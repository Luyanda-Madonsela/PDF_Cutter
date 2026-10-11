import re
import json
import asyncio
from core import logger
from llm import ai_settings, resolve, complete, BudgetExceeded

COMMON_RULES = """- Coordinates: y_start and y_end are integers 0-1000 relative to page height (0 = top edge, 1000 = bottom edge). Segments are in top-to-bottom order and do not overlap.
- EXCLUDE page headers, footers, page numbers, "Copyright reserved", "Please turn over / Blaai om", exam centre / candidate boxes.
- NEVER erase round-bracket mark allocations like (3), ticks or answer text; "exclude" boxes must be tight and only cover the listed items.
- "exclude" boxes are tight bounding boxes [ymin, xmin, ymax, xmax] in 0-1000 coordinates of text that must be ERASED from the image.
- "review": set to a short reason (string) when a segment needs a human to check it, e.g. a number/total that must be erased overlaps a diagram or other text so erasing it would damage content (in that case do NOT put it in exclude), the question layout is unusual (two columns, rotated page), or you are unsure where it starts/stops. Otherwise null.
- If the TOP of the page continues an item from the previous page (content before any new number), output a segment with label "CONTINUED"."""

QP_PROMPT = """You are analysing ONE page image from a South African high school exam QUESTION PAPER (NSC/IEB/DBE/provincial, any subject, English or Afrikaans).
Find where every sub-question region starts and stops vertically on this page.

Rules:
- Split at SUB-QUESTION level: 1.1, 1.2, 2.1 ... Deeper parts (1.1.1, 1.1.2, (a), (b)) stay INSIDE their parent sub-question region (1.1). If a main question has no sub-questions, use the main number, e.g. "3".
- NEVER merge or skip sub-questions: EVERY distinct sub-question number that starts on this page gets its OWN segment. First list them all in "labels_on_page" (top to bottom), then output exactly one segment per listed label (plus an optional leading "CONTINUED" segment).
- Headings "QUESTION 1" / "VRAAG 1" and "SECTION A" / "AFDELING A" (+ section instructions) are NOT part of any segment: start the segment just BELOW them. Shared intro text, passages, diagrams or tables between the heading and the first sub-question belong to that FIRST sub-question.
- Include diagrams, tables and answer options belonging to a sub-question. Keep round-bracket mark allocations like (3).
- ANSWER SPACES must be LEFT OUT of the crop: ruled/dotted writing lines (______ or ......), empty answer boxes/frames, blank grids or tables the candidate must fill in, "Answer:" / "Antwoord:" blanks, and empty space reserved for working. End a segment ABOVE answer space at its bottom, and list every answer-space band (also ones between deeper parts like 1.1.1 and 1.1.2) in "answer_spaces" as [y_start, y_end]. Multiple-choice options, printed diagrams, given tables and graphs are NOT answer spaces.
- "marks": total marks for that sub-question = sum of all round-bracket allocations like (2), (3) in it (including deeper parts). null if none visible.
- ERASE via "exclude": (1) the sub-question's OWN number printed at its start (e.g. the "1.1" before the text; NOT the deeper 1.1.1 / (a) numbers); (2) "QUESTION n"/"VRAAG n"/"SECTION X" headings; (3) square-bracket question totals like [16]; (4) section totals like "TOTAL SECTION A: 50"; (5) paper totals like "TOTAL: 150" / "GRAND TOTAL". Segments should end above totals where possible.
""" + COMMON_RULES + """
- If the page has no questions (cover, instructions, information/formula sheet, blank page, answer sheet), return empty lists.

Respond with ONLY JSON, no markdown:
{"labels_on_page":["1.1","1.2"],"segments":[{"label":"1.1","y_start":120,"y_end":340,"marks":7,"review":null},{"label":"1.2","y_start":340,"y_end":420,"marks":3,"review":null}],"exclude":[[122,60,135,95],[425,880,440,930]],"answer_spaces":[[250,290]]}"""

MEMO_PROMPT = """You are analysing ONE page image from a South African high school exam MARKING GUIDELINE / MEMORANDUM.
Find where the answer/marking region for every sub-question starts and stops vertically on this page.

Rules:
- Split at SUB-QUESTION level: 1.1, 1.2, 2.1 ... Answers for deeper parts (1.1.1, 1.1.2, (a)) stay INSIDE their parent sub-question region (1.1). If a main question has no sub-questions, use the main number.
- Question numbers often appear in a left-hand column of a table; a region spans all rows for that sub-question.
- EVERY distinct sub-question that starts on this page gets its own segment. First list them in "labels_on_page".
- "marks": marks for that sub-question if shown, else null.
- ERASE via "exclude": the sub-question's OWN number (e.g. "1.1" in the left column), "QUESTION n"/"VRAAG n" headings, square-bracket totals like [16], section and paper totals.
""" + COMMON_RULES + """
- Pages with only general marking notes, principles, cover info or blank have empty lists.

Respond with ONLY JSON, no markdown:
{"labels_on_page":["1.1"],"segments":[{"label":"1.1","y_start":120,"y_end":340,"marks":7,"review":null}],"exclude":[[122,40,135,80]]}"""

ADDENDUM_PROMPT = """You are analysing ONE page image from an ADDENDUM / ANNEXURE / BYLAE of a South African exam paper. It contains graphs, diagrams, maps, tables, sources or extracts that students need for specific questions.
Split the page into items (one per figure/table/source/extract).

Rules:
- "label": the question number the item is for, as printed (e.g. "FOR QUESTION 4.1" -> "4.1", "QUESTION 2" -> "2", "SOURCE 1A (Question 1.2)" -> "1.2"). Use "GENERAL" for items not tied to one question (formula/information sheets, general answer sheets, cover pages with content).
- "marks": always null.
- "exclude": usually empty.
""" + COMMON_RULES + """
- Blank pages or pure cover/instruction pages have empty lists.

Respond with ONLY JSON, no markdown:
{"labels_on_page":["4.1"],"segments":[{"label":"4.1","y_start":80,"y_end":600,"marks":null,"review":null}],"exclude":[]}"""

ERRATA_PROMPT = """You are analysing ONE page image from an ERRATUM / ERRATA notice that corrects mistakes in a South African exam paper.
Split the page into correction items - one per question being corrected.

Rules:
- "label": the question number being corrected (e.g. "QUESTION 3.2" -> "3.2"). Use "GENERAL" for corrections not tied to a question.
- A segment covers the full correction text (and any replacement diagram) for that question. Do NOT include letterheads, addresses, greetings, signatures.
- "marks": always null. "exclude": usually empty.
""" + COMMON_RULES + """

Respond with ONLY JSON, no markdown:
{"labels_on_page":["3.2"],"segments":[{"label":"3.2","y_start":300,"y_end":420,"marks":null,"review":null}],"exclude":[]}"""

PROMPTS = {"question_paper": QP_PROMPT, "memo": MEMO_PROMPT, "addendum": ADDENDUM_PROMPT, "errata": ERRATA_PROMPT}

META_PROMPT = """This is the first page of a South African high school exam document.
Extract metadata. Respond with ONLY JSON, no markdown:
{"subject":"Mathematics","grade":"12","year":"2024","session":"Nov","province":"National","paper":"1","language":"English","doc_type":"question_paper","school":"","assessment":"","term":"","curriculum":"","qualification":"","variant":""}
Rules:
- subject: short English subject name (e.g. "Mathematics", "Physical Sciences", "Life Sciences", "Accounting", "English HL", "Afrikaans FAL"). Translate Afrikaans names.
- grade: digits only. year: 4 digits.
- session (time of year): one of "Feb/Mar", "May/Jun", "Sep", "Nov", "Exemplar".
- province: issuing body. One of "GP", "KZN", "WC", "EC", "FS", "LP", "MP", "NW", "NC", "IEB", or "National" for national DBE / NSC papers. Look at logos, headers and department names.
- paper: digits only ("1","2","3") or "" if none.
- language: "English" or "Afrikaans" (language of the document).
- doc_type: "memo" for marking guidelines / memorandum / nasienriglyne; "addendum" for addendum / annexure / bylae / answer book inserts with diagrams; "errata" for erratum / errata / correction notices; otherwise "question_paper".
- school: ONLY for tests set by a single school (school name/crest in the header, no department or IEB branding): the school's name, e.g. "Westville Boys' High School". Otherwise "".
- assessment: for school tests one of "Test", "Control Test", "Exam", "Assignment", "Investigation", "Project"; otherwise "".
- term: for school tests the term number "1"-"4" if stated (or implied by month: Jan-Mar 1, Apr-Jun 2, Jul-Sep 3, Oct-Dec 4); otherwise "". For school tests leave province "".
- curriculum: "cambridge" for Cambridge Assessment International Education (CAIE/CIE: IGCSE, O Level, AS & A Level, Checkpoint), "ib" for International Baccalaureate Diploma, "nbt" for National Benchmark Tests; otherwise "".
- qualification: Cambridge syllabus code (e.g. "0580", "0625", "9709", "1112"); for IB one of "IB-MAA-SL", "IB-MAA-HL", "IB-MAI-SL", "IB-MAI-HL", "IB-PHY-SL", "IB-PHY-HL", "IB-CHE-SL", "IB-CHE-HL"; for NBT "NBT-AQL" or "NBT-MAT"; otherwise "".
- For Cambridge, "0580/22" means paper "2" variant "2" (component 22). session: "Feb/Mar", "May/Jun" or "Oct/Nov" (Checkpoint: "Apr" or "Oct"). Mark schemes are doc_type "memo"; inserts are "addendum".
- variant: Cambridge variant digit ("1"-"3"); for IB the time zone digit ("TZ1" -> "1", "TZ2" -> "2", no time zone -> "0"); otherwise "".
- Use "" for anything not visible."""


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(m.group(0))


def to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def ask_json(prompt: str, img_b64: str, session_id: str) -> dict:
    cfg = resolve(await ai_settings())
    last_err = None
    for attempt in range(3):
        try:
            return parse_json(await complete(cfg, prompt, img_b64, f"{session_id}-{attempt}"))
        except BudgetExceeded:
            raise
        except Exception as e:
            last_err = e
            logger.warning(f"{session_id} attempt {attempt} failed: {e}")
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI failed ({session_id}): {last_err}")


TOPIC_RULE = """
- "topic": add this field to every segment: the curriculum topic of that sub-question, EXACTLY one of: {topics}. Pick the closest match."""


DIFFICULTY_SCALE = """"Easy" = recall or a routine one-step procedure; "Medium" = a routine multi-step procedure or familiar application; "Hard" = complex or non-routine problem solving, proofs, multi-concept reasoning or unfamiliar contexts. Judge for a typical learner at this grade/level and consider the marks allocated."""
DIFFICULTY_RULE = """
- "difficulty": add this field to every segment: exactly one of "Easy", "Medium", "Hard". """ + DIFFICULTY_SCALE
RATE_PROMPT = """This image is ONE question from a {context} exam question paper.
Rate its difficulty: """ + DIFFICULTY_SCALE + """
Respond with ONLY JSON, no markdown: {{"difficulty":"Medium"}}"""
LEVELS = ("Easy", "Medium", "Hard")


def norm_difficulty(v):
    low = str(v or "").strip().lower()
    if low.startswith(("easy", "beginner")):
        return "Easy"
    if low.startswith(("med", "moderate", "intermediate")):
        return "Medium"
    if low.startswith(("hard", "difficult", "challeng")):
        return "Hard"
    return None


async def rate_difficulty(img_b64: str, session_id: str, context: str):
    return norm_difficulty((await ask_json(RATE_PROMPT.format(context=context), img_b64, session_id)).get("difficulty"))


async def detect_segments(img_b64: str, session_id: str, doc_type: str, topics=None):
    prompt = PROMPTS.get(doc_type, QP_PROMPT)
    if doc_type == "question_paper":
        prompt += DIFFICULTY_RULE
    if topics:
        prompt += TOPIC_RULE.format(topics=json.dumps(topics))
    data = await ask_json(prompt, img_b64, session_id)
    out = []
    for s in data.get("segments", []):
        y0 = max(0, min(1000, int(s["y_start"])))
        y1 = max(0, min(1000, int(s["y_end"])))
        if y1 - y0 > 5:
            review = s.get("review")
            out.append({"label": str(s.get("label", "CONTINUED")).strip(), "y0": y0, "y1": y1,
                        "marks": to_int(s.get("marks")), "review": str(review).strip() if review else None,
                        "topic": str(s["topic"]).strip() if s.get("topic") else None,
                        "difficulty": norm_difficulty(s.get("difficulty"))})
    excl = [[max(0, min(1000, int(v))) for v in b] for b in data.get("exclude", []) if isinstance(b, list) and len(b) == 4]
    bands = [(int(b[0]), int(b[1])) for b in data.get("answer_spaces", []) if isinstance(b, list) and len(b) == 2 and int(b[1]) > int(b[0])]
    return cut_bands(sorted(out, key=lambda s: s["y0"]), bands), excl


def cut_bands(segs: list, bands: list) -> list:
    """Remove answer-space bands from segments; the pieces keep the label so they stitch back together."""
    out = []
    for s in segs:
        pieces = [(s["y0"], s["y1"])]
        for b0, b1 in sorted(bands):
            pieces = [q for a, z in pieces for q in ((a, min(z, b0)), (max(a, b1), z)) if q[1] - q[0] > 5] if any(a < b1 and b0 < z for a, z in pieces) else pieces
        for i, (a, z) in enumerate(pieces):
            out.append({**s, "y0": a, "y1": z, **({} if i == 0 else {"marks": None, "review": None})})
    return out


async def detect_meta(img_b64: str, session_id: str) -> dict:
    try:
        data = await ask_json(META_PROMPT, img_b64, session_id)
        return {k: str(v or "").strip() for k, v in data.items()}
    except BudgetExceeded:
        raise
    except Exception as e:
        logger.warning(f"Meta detection failed: {e}")
        return {}
