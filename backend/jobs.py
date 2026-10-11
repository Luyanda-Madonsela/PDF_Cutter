import re
import uuid
import base64
import asyncio
from pathlib import Path
from typing import List, Optional
import pymupdf
from core import db, logger, put_object, get_object, APP_NAME
from models import Job, JobMeta, Question, Part, PaperSet, DocSummary
from ai import detect_segments, detect_meta
from catalogue import locate
from imaging import page_jpeg, crop_parts, finalize, x_bounds, union_col, to_png

CONCURRENCY = 6
SESSIONS = [(("feb", "mar"), "Feb/Mar"), (("may", "jun"), "May/Jun"), (("sep",), "Sep"), (("nov",), "Nov"), (("exem",), "Exemplar")]
PROVINCES = [("gauteng", "GP"), ("kwazulu", "KZN"), ("kzn", "KZN"), ("western cape", "WC"), ("wced", "WC"), ("eastern cape", "EC"),
             ("free state", "FS"), ("limpopo", "LP"), ("mpumalanga", "MP"), ("north west", "NW"), ("northern cape", "NC"),
             ("ieb", "IEB"), ("national", "National"), ("dbe", "National"), ("nsc", "National")]
PROVINCE_CODES = {"GP", "KZN", "WC", "EC", "FS", "LP", "MP", "NW", "NC", "IEB"}
DOC_SUFFIX = {"memo": "MEMO", "addendum": "ADDENDUM", "errata": "ERRATA"}
KEY_FIELDS = ("subject", "grade", "year", "session", "paper")
SOFT_FIELDS = ("province", "language")
ACTIVE = ("queued", "classifying", "waiting", "ready", "processing")


# ---------- naming ----------
def canon_session(s: str) -> str:
    low = (s or "").strip().lower()
    for keys, val in SESSIONS:
        if low and any(k in low for k in keys):
            return val
    return (s or "").strip()


def canon_province(s: str) -> str:
    raw = (s or "").strip()
    if raw.upper() in PROVINCE_CODES:
        return raw.upper()
    low = raw.lower()
    for key, code in PROVINCES:
        if key in low:
            return code
    return raw


def canon_meta(m: JobMeta) -> JobMeta:
    m.session = canon_session(m.session)
    m.province = canon_province(m.province)
    m.grade = re.sub(r"\D", "", m.grade or "")
    m.paper = re.sub(r"\D", "", m.paper or "")
    m.language = (m.language or "").strip().capitalize()
    return m


def camel(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", s or "") if w)


def safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9.\-]", "_", label)


def norm_label(label: str) -> str:
    m = re.search(r"\d+(?:\.\d+)*", label or "")
    return m.group(0) if m else (label or "").strip().lower()


def set_base_name(meta: JobMeta, fallback: str) -> str:
    if not meta.subject:
        return camel(Path(fallback).stem)
    bits = [camel(meta.subject), f"Gr{meta.grade}" if meta.grade else "", meta.year, camel(meta.session),
            camel(meta.province), f"P{meta.paper}" if meta.paper else ""]
    return "_".join(b for b in bits if b)


def renumber(job: Job, set_base: str):
    suffix = DOC_SUFFIX.get(job.meta.doc_type)
    job.base_name = f"{set_base}_{suffix}" if suffix else set_base
    seen = {}
    for i, q in enumerate(job.questions, start=1):
        lab = safe_label(q.label)
        seen[lab] = seen.get(lab, 0) + 1
        dup = f"_{seen[lab]}" if seen[lab] > 1 else ""
        marks = f"_{q.marks}marks" if q.marks is not None and job.meta.doc_type in ("question_paper", "memo") else ""
        q.order = i
        q.filename = f"{i:03d}_{job.base_name}_Q{lab}{dup}{marks}.png"


# ---------- persistence ----------
async def load_job(job_id: str) -> Optional[Job]:
    doc = await db.jobs.find_one({"_id": job_id, "is_deleted": False})
    return Job.from_mongo(doc) if doc else None


async def load_set(set_id: str) -> Optional[PaperSet]:
    doc = await db.sets.find_one({"_id": set_id, "is_deleted": False}) if set_id else None
    return PaperSet.from_mongo(doc) if doc else None


async def set_jobs(set_id: str) -> List[Job]:
    docs = await db.jobs.find({"set_id": set_id, "is_deleted": False}).sort("created_at", 1).to_list(100)
    return [Job.from_mongo(d) for d in docs]


async def save_job(job: Job):
    await db.jobs.replace_one({"_id": job.id}, job.to_mongo())


async def set_fields(job_id: str, **fields):
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})


# ---------- linking ----------
def pick(jobs: List[Job], t: str) -> List[Job]:
    return [j for j in jobs if j.meta.doc_type == t]


def compute_links(jobs: List[Job]) -> dict:
    qps = [j for j in pick(jobs, "question_paper") if j.status == "done"]
    memos = [j for j in pick(jobs, "memo") if j.status == "done"]
    qp, memo = (qps[0] if qps else None), (memos[0] if memos else None)
    links, extras = {}, {"general": [], "unlinked": [], "memo_unmatched": []}
    if not qp:
        return {"links": links, "extras": extras, "qp_id": None}
    for q in qp.questions:
        links[q.id] = {"memo": None, "addenda": [], "errata": [], "flags": []}
    qnorm = [(q, norm_label(q.label)) for q in qp.questions]

    if memo:
        by_label = {}
        for mq in memo.questions:
            by_label.setdefault(norm_label(mq.label), mq)
        used = set()
        for q, n in qnorm:
            mq = by_label.get(n)
            if mq:
                used.add(mq.id)
                links[q.id]["memo"] = {"job_id": memo.id, "qid": mq.id}
        extras["memo_unmatched"] = [{"job_id": memo.id, "qid": mq.id, "label": mq.label} for mq in memo.questions if mq.id not in used]

    for kind, key in (("addendum", "addenda"), ("errata", "errata")):
        for j in pick(jobs, kind):
            if j.status != "done":
                continue
            for item in j.questions:
                ref = {"job_id": j.id, "qid": item.id, "label": item.label, "doc_type": kind}
                n = norm_label(item.label)
                if not re.match(r"^\d", n):
                    extras["general"].append(ref)
                    continue
                hits = [q for q, qn in qnorm if qn == n or qn.startswith(n + ".") or n.startswith(qn + ".")]
                for q in hits:
                    links[q.id][key].append(ref)
                if not hits:
                    extras["unlinked"].append(ref)

    for q in qp.questions:
        if q.reviewed:
            continue
        f = list(q.flags)
        if memo and not links[q.id]["memo"]:
            f.append("No matching memo answer found")
        links[q.id]["flags"] = f
    return {"links": links, "extras": extras, "qp_id": qp.id}


# ---------- sets ----------
def set_status(jobs: List[Job]) -> str:
    types = {j.meta.doc_type for j in jobs if j.status not in ("queued", "classifying")}
    if not any(j.status in ("queued", "classifying") for j in jobs):
        if "question_paper" not in types:
            return "needs_paper"
        if "memo" not in types:
            return "needs_memo"
    if any(j.status == "error" for j in jobs):
        return "error"
    if jobs and all(j.status == "done" for j in jobs):
        return "done"
    return "processing"


async def refresh_set(set_id: str):
    s = await load_set(set_id)
    if not s:
        return
    jobs = await set_jobs(set_id)
    status = set_status(jobs)
    if status not in ("needs_paper", "needs_memo"):
        waiting = [j.id for j in jobs if j.status == "waiting"]
        if waiting:
            await db.jobs.update_many({"_id": {"$in": waiting}}, {"$set": {"status": "ready"}})
            for j in jobs:
                if j.id in waiting:
                    j.status = "ready"
    links = compute_links(jobs)
    qp = next((j for j in jobs if j.id == links["qp_id"]), None)
    docs = [DocSummary(job_id=j.id, doc_type=j.meta.doc_type, filename=j.filename, status=j.status,
                       pages_done=j.pages_done, total_pages=j.total_pages).model_dump() for j in jobs]
    await db.sets.update_one({"_id": set_id}, {"$set": {
        "status": set_status(jobs), "docs": docs, "question_count": len(qp.questions) if qp else 0,
        "flagged": sum(1 for v in links["links"].values() if v["flags"])}})


def compatible(a: JobMeta, b: JobMeta) -> bool:
    return all(not getattr(a, k) or not getattr(b, k) or getattr(a, k).lower() == getattr(b, k).lower() for k in SOFT_FIELDS)


async def assign_set(job: Job) -> str:
    m = job.meta
    if m.subject and m.grade and m.year:
        query = {"is_deleted": False, "mode": "bulk"}
        for k in KEY_FIELDS:
            query[f"meta.{k}"] = {"$regex": f"^{re.escape(getattr(m, k))}$", "$options": "i"}
        async for d in db.sets.find(query).sort("created_at", 1):
            s = PaperSet.from_mongo(d)
            have = {x.doc_type for x in s.docs}
            if compatible(s.meta, m) and not (m.doc_type in ("question_paper", "memo") and m.doc_type in have):
                if m.doc_type == "question_paper":
                    await update_set_meta(s, m)
                return s.id
    s = PaperSet(meta=m.model_copy(), mode="bulk")
    s.base_name = set_base_name(s.meta, job.filename)
    await db.sets.insert_one(s.to_mongo())
    return s.id


async def update_set_meta(s: PaperSet, meta: JobMeta):
    s.meta = meta.model_copy(update={"doc_type": "question_paper"})
    s.base_name = set_base_name(s.meta, "paper")
    await db.sets.update_one({"_id": s.id}, {"$set": {"meta": s.meta.model_dump(), "base_name": s.base_name}})


# ---------- pipeline ----------
async def classify_job(job_id: str):
    job = await load_job(job_id)
    if not job:
        return
    try:
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        n = doc.page_count
        b64 = base64.b64encode(page_jpeg(doc, 0)).decode()
        doc.close()
        existing = await load_set(job.set_id) if job.set_id else None
        if job.forced_type and job.forced_type != "question_paper" and existing and existing.meta.subject:
            raw = existing.meta.model_dump()  # attaching to a known set: no need to re-read the cover
        else:
            raw = await detect_meta(b64, f"{job_id}-meta")
        meta = canon_meta(JobMeta(**{k: v for k, v in raw.items() if k in JobMeta.model_fields}))
        if meta.doc_type not in DOC_SUFFIX and meta.doc_type != "question_paper":
            meta.doc_type = "question_paper"
        if job.forced_type:
            meta.doc_type = job.forced_type
        job.meta, job.total_pages = meta, n
        if not job.set_id:
            job.set_id = await assign_set(job)
        else:
            s = await load_set(job.set_id)
            if s and (meta.doc_type == "question_paper" or not s.meta.subject):
                await update_set_meta(s, meta)
        await set_fields(job_id, meta=meta.model_dump(), total_pages=n, set_id=job.set_id, status="waiting", error=None)
    except Exception as e:
        logger.exception("Classify failed")
        await set_fields(job_id, status="error", error=f"Could not read document: {e}")
    if job.set_id:
        await refresh_set(job.set_id)


def merge_groups(page_segs: list) -> list:
    groups = []
    for p, segs in enumerate(page_segs):
        for s in segs:
            label = s["label"]
            is_cont = label.upper() in ("CONTINUED", "CONT", "") or (groups and groups[-1]["label"] == label)
            part = Part(page=p, y0=s["y0"], y1=s["y1"])
            if is_cont and groups:
                g = groups[-1]
            elif not is_cont:
                g = {"label": label, "parts": [], "marks": [], "flags": [], "topic": None}
                groups.append(g)
            else:
                continue
            g["parts"].append(part)
            g["marks"].append(s.get("marks"))
            g["topic"] = g["topic"] or s.get("topic")
            if s.get("review"):
                g["flags"].append(s["review"])
    return groups


def sum_marks(values):
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def match_topic(topic, topics):
    if not topic or not topics:
        return None
    return next((t for t in topics if t.lower() == topic.lower()), None) or next((t for t in topics if topic.lower() in t.lower() or t.lower() in topic.lower()), None)


async def upload_question(job_id: str, img, label: str, parts, marks, flags, qid: str = None, topic=None) -> Question:
    path = await put_object(f"{APP_NAME}/jobs/{job_id}/{uuid.uuid4()}.png", to_png(img), "image/png")
    return Question(id=qid or str(uuid.uuid4()), label=label, storage_path=path, parts=parts, marks=marks, flags=flags, topic=topic,
                    pages=sorted({p.page + 1 for p in parts}), width=img.width, height=img.height)


ERASE_FLAG = "Erase pending approval"


def erase_proposals(job: Job, parts) -> List[List[int]]:
    """AI-suggested erase boxes that fall inside the question's crop regions."""
    out = []
    for p in parts:
        boxes = job.page_masks[p.page] if p.page < len(job.page_masks) else []
        out += [[p.page, *b] for b in boxes if b[2] > p.y0 and b[0] < p.y1 and [p.page, *b] not in out]
    return out


def masks_from(applied: List[List[int]], n_pages: int) -> list:
    masks = [[] for _ in range(n_pages)]
    for page, *box in applied:
        if page < n_pages:
            masks[page].append(box)
    return masks


async def rebuild_question(job: Job, doc, label: str, parts, marks, flags, qid: str, reviewed: bool = False, topic=None,
                           erase_applied=None, erase_status: str = "none") -> Question:
    applied = erase_applied or []
    crops = await asyncio.to_thread(crop_parts, doc, parts, {}, masks_from(applied, doc.page_count))
    col = job.content_col or None
    for c in crops:
        col = union_col(col, x_bounds(c))
    q = await upload_question(job.id, await asyncio.to_thread(finalize, crops, col), label, parts, marks, flags, qid, topic)
    q.reviewed, q.erase_applied, q.erase_status = reviewed, applied, erase_status
    return q


async def process_job(job_id: str):
    job = await load_job(job_id)
    if not job:
        return
    try:
        s = await load_set(job.set_id)
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        n = doc.page_count
        await set_fields(job_id, total_pages=n, pages_done=0, error=None)
        jpgs = [page_jpeg(doc, i) for i in range(n)]
        b64s = [base64.b64encode(j).decode() for j in jpgs]
        page_paths = await asyncio.gather(*[put_object(f"{APP_NAME}/jobs/{job_id}/page_{i}.jpg", j, "image/jpeg") for i, j in enumerate(jpgs)])
        doc_type = job.meta.doc_type
        topics = locate(s.meta).get("topics", []) if s and doc_type == "question_paper" else []
        page_masks = [[] for _ in range(n)]
        sem = asyncio.Semaphore(CONCURRENCY)
        done = {"n": 0}

        async def run(i):
            async with sem:
                segs, excl = await detect_segments(b64s[i], f"{job_id}-p{i + 1}", doc_type, topics)
                page_masks[i] = excl
                done["n"] += 1
                await set_fields(job_id, pages_done=done["n"])
                return segs

        groups = merge_groups(await asyncio.gather(*[run(i) for i in range(n)]))

        def evict(cache, first):
            for k in [k for k in cache if k < first]:
                del cache[k]

        # pass 1: shared content column so every image has the same crop width
        cache, col = {}, None
        for g in groups:
            evict(cache, g["parts"][0].page)
            for c in await asyncio.to_thread(crop_parts, doc, g["parts"], cache, []):
                col = union_col(col, x_bounds(c))
        # pass 2: final images
        cache, questions = {}, []
        for g in groups:
            evict(cache, g["parts"][0].page)
            crops = await asyncio.to_thread(crop_parts, doc, g["parts"], cache, [])  # no erasing without human approval
            marks = sum_marks(g["marks"])
            flags = list(dict.fromkeys(g["flags"]))
            if doc_type == "question_paper" and marks is None:
                flags.append("Marks not found")
            topic = match_topic(g["topic"], topics)
            if topics and not topic:
                flags.append("Topic not set")
            img = await asyncio.to_thread(finalize, crops, col)
            q = await upload_question(job_id, img, g["label"], g["parts"], marks, flags, topic=topic)
            if erase_proposals(Job(filename="", page_masks=page_masks), g["parts"]):
                q.erase_status = "pending"
                q.flags.append(ERASE_FLAG)
            questions.append(q)
        doc.close()

        job = await load_job(job_id)
        job.page_paths, job.questions, job.page_masks, job.content_col = page_paths, questions, page_masks, col or []
        job.status, job.pages_done = "done", n
        renumber(job, s.base_name if s else set_base_name(job.meta, job.filename))
        await save_job(job)
    except Exception as e:
        logger.exception("Job failed")
        await set_fields(job_id, status="error", error=str(e))
    if job.set_id:
        await refresh_set(job.set_id)


async def claim_next():
    for st, new in (("queued", "classifying"), ("ready", "processing")):
        doc = await db.jobs.find_one_and_update({"status": st, "is_deleted": False}, {"$set": {"status": new}}, sort=[("created_at", 1)])
        if doc:
            return doc["_id"], new
    return None, None


async def worker_loop():
    while True:
        try:
            job_id, stage = await claim_next()
            if not job_id:
                await asyncio.sleep(2)
                continue
            job = await load_job(job_id)
            if job and job.set_id:
                await refresh_set(job.set_id)
            await (classify_job(job_id) if stage == "classifying" else process_job(job_id))
        except Exception:
            logger.exception("Worker error")
            await asyncio.sleep(5)
