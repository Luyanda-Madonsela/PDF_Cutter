import re
import json
import asyncio
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
from core import LLM_KEY, logger

SEGMENT_PROMPT = """You are analysing ONE page image from a South African high school exam past paper (NSC/IEB/DBE, any subject, English or Afrikaans).
Find where every question/sub-question region starts and stops vertically on this page.
{memo_note}
Rules:
- Split at SUB-QUESTION level: e.g. 1.1, 1.2, 2.1 ... Deeper parts (1.1.1, 1.1.2, (a), (b)) stay INSIDE their parent sub-question region (1.1).
- If a main question has no sub-questions, use the main number, e.g. "3".
- The "QUESTION 1 / VRAAG 1" heading and any shared intro text, passage, diagram or table that comes before the first sub-question belongs to the region of that FIRST sub-question (start the region at the heading).
- Include diagrams, tables, answer options and mark allocations belonging to a sub-question in its region.
- If the TOP of the page continues a question from the previous page (content before any new question number), output a segment with label "CONTINUED".
- EXCLUDE page headers, footers, page numbers, "Copyright reserved", "Please turn over / Blaai om", exam centre boxes.
- If the page has no questions (cover page, instructions, information/formula sheet, blank page, answer sheet, "TOTAL" only), return an empty segments list.
- Coordinates: y_start and y_end are integers 0-1000 relative to page height (0 = top edge, 1000 = bottom edge). Segments must be in top-to-bottom order and not overlap. Each segment should extend down to just before the next segment starts.

Respond with ONLY JSON, no markdown:
{{"segments":[{{"label":"1.1","y_start":120,"y_end":340}}]}}"""

MEMO_NOTE = """This page is from a MARKING GUIDELINE / MEMORANDUM. Each region is the answer and marking for one sub-question.
Question numbers often appear in a left-hand column of a table; a region spans all table rows for that sub-question.
Pages that contain only general marking notes, principles or cover info have no segments."""

META_PROMPT = """This is the first page (usually the cover) of a South African high school exam document.
Extract metadata. Respond with ONLY JSON, no markdown:
{"subject":"Mathematics","grade":"12","year":"2024","session":"November","paper":"1","language":"English","doc_type":"question_paper"}
Rules:
- subject: short English subject name (e.g. "Mathematics", "Physical Sciences", "Life Sciences", "Accounting", "English HL", "Afrikaans FAL"). Translate Afrikaans names.
- grade: digits only. year: 4 digits. session: one of "February","March","May","June","September","November","Exemplar" (English).
- paper: digits only ("1","2","3") or "" if none.
- doc_type: "memo" if it is a marking guideline / memorandum / nasienriglyne, otherwise "question_paper".
- Use "" for anything not visible."""


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(m.group(0))


async def ask_json(prompt: str, img_b64: str, session_id: str) -> dict:
    last_err = None
    for attempt in range(3):
        try:
            chat = LlmChat(
                api_key=LLM_KEY,
                session_id=f"{session_id}-{attempt}",
                system_message="You are a precise document layout analyser. Output only valid JSON.",
            ).with_model("gemini", "gemini-3-flash-preview")
            text = ""
            async for ev in chat.stream_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=img_b64)])):
                if isinstance(ev, TextDelta):
                    text += ev.content
                elif isinstance(ev, StreamDone):
                    break
            return parse_json(text)
        except Exception as e:
            last_err = e
            logger.warning(f"{session_id} attempt {attempt} failed: {e}")
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI failed ({session_id}): {last_err}")


async def detect_segments(img_b64: str, session_id: str, memo: bool) -> list:
    data = await ask_json(SEGMENT_PROMPT.format(memo_note=MEMO_NOTE if memo else ""), img_b64, session_id)
    out = []
    for s in data.get("segments", []):
        y0 = max(0, min(1000, int(s["y_start"])))
        y1 = max(0, min(1000, int(s["y_end"])))
        if y1 - y0 > 5:
            out.append({"label": str(s.get("label", "CONTINUED")).strip(), "y0": y0, "y1": y1})
    return sorted(out, key=lambda s: s["y0"])


async def detect_meta(img_b64: str, session_id: str) -> dict:
    try:
        data = await ask_json(META_PROMPT, img_b64, session_id)
        return {k: str(v or "").strip() for k, v in data.items()}
    except Exception as e:
        logger.warning(f"Meta detection failed: {e}")
        return {}
