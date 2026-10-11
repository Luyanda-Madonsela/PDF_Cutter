import re
import uuid
import base64
import asyncio
from pathlib import Path
import pymupdf
from core import db, logger, put_object, get_object, APP_NAME
from models import Job, JobMeta, Question, Part
from ai import detect_segments, detect_meta
from imaging import page_jpeg, render_question, to_png

CONCURRENCY = 6
SESSIONS = [(("feb", "mar"), "Feb/Mar"), (("may", "jun"), "May/Jun"), (("sep",), "Sep"), (("nov",), "Nov"), (("exem",), "Exemplar")]
PROVINCES = [("gauteng", "GP"), ("kwazulu", "KZN"), ("kzn", "KZN"), ("western cape", "WC"), ("wced", "WC"), ("eastern cape", "EC"),
             ("free state", "FS"), ("limpopo", "LP"), ("mpumalanga", "MP"), ("north west", "NW"), ("northern cape", "NC"),
             ("ieb", "IEB"), ("national", "National"), ("dbe", "National"), ("nsc", "National")]
PROVINCE_CODES = {"GP", "KZN", "WC", "EC", "FS", "LP", "MP", "NW", "NC", "IEB", "National"}


def canon_session(s: str) -> str:
    low = (s or "").strip().lower()
    for keys, val in SESSIONS:
        if low and any(k in low for k in keys):
            return val
    return (s or "").strip()


def canon_province(s: str) -> str:
    raw = (s or "").strip()
    if raw.upper() in PROVINCE_CODES or raw == "National":
        return "National" if raw.lower() == "national" else raw.upper()
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
    return m


def camel(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", s or "") if w)


def slug(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s or "")).strip("_")


def safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9.\-]", "_", label)


def norm_label(label: str) -> str:
    return re.sub(r"[^0-9a-z.]", "", (label or "").lower()).strip(".")


def compute_base_name(job: Job) -> str:
    m = job.meta
    if not m.subject:
        return slug(Path(job.filename).stem)
    bits = [camel(m.subject), f"Gr{m.grade}" if m.grade else "", m.year, camel(m.session), camel(m.province),
            f"P{m.paper}" if m.paper else "", "MEMO" if m.doc_type == "memo" else ""]
    return "_".join(b for b in bits if b)


def renumber(job: Job):
    job.base_name = compute_base_name(job)
    seen = {}
    for i, q in enumerate(job.questions, start=1):
        lab = safe_label(q.label)
        seen[lab] = seen.get(lab, 0) + 1
        suffix = f"_{seen[lab]}" if seen[lab] > 1 else ""
        q.order = i
        marks = f"_{q.marks}marks" if q.marks is not None else ""
        q.filename = f"{i:03d}_{job.base_name}_Q{lab}{suffix}{marks}.png"


async def load_job(job_id: str):
    doc = await db.jobs.find_one({"_id": job_id, "is_deleted": False})
    return Job.from_mongo(doc) if doc else None


async def save_job(job: Job):
    await db.jobs.replace_one({"_id": job.id}, job.to_mongo())


async def set_fields(job_id: str, **fields):
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})


async def try_pair(job: Job):
    m = job.meta
    if job.paired_job_id or not (m.subject and m.grade and m.year):
        return
    other_type = "question_paper" if m.doc_type == "memo" else "memo"
    query = {"is_deleted": False, "status": "done", "paired_job_id": None, "_id": {"$ne": job.id},
             "meta.doc_type": other_type}
    for k in ("subject", "grade", "year", "session", "paper", "province"):
        query[f"meta.{k}"] = {"$regex": f"^{re.escape(getattr(m, k))}$", "$options": "i"}
    other = await db.jobs.find_one(query, sort=[("created_at", -1)])
    if other:
        await set_fields(job.id, paired_job_id=other["_id"])
        await set_fields(other["_id"], paired_job_id=job.id)


async def unpair(job: Job):
    if job.paired_job_id:
        await set_fields(job.paired_job_id, paired_job_id=None)
        await set_fields(job.id, paired_job_id=None)


def sum_marks(values):
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


async def build_question(job_id: str, doc, label: str, parts, cache: dict, masks: list, marks=None, qid: str = None) -> Question:
    img = await asyncio.to_thread(render_question, doc, parts, cache, masks)
    path = await put_object(f"{APP_NAME}/jobs/{job_id}/{uuid.uuid4()}.png", to_png(img), "image/png")
    return Question(id=qid or str(uuid.uuid4()), label=label, storage_path=path, parts=parts,
                    pages=sorted({p.page + 1 for p in parts}), width=img.width, height=img.height, marks=marks)


def merge_groups(page_segs: list) -> list:
    groups = []
    for p, segs in enumerate(page_segs):
        for s in segs:
            label = s["label"]
            is_cont = label.upper() in ("CONTINUED", "CONT", "") or (groups and groups[-1]["label"] == label)
            part = Part(page=p, y0=s["y0"], y1=s["y1"])
            if is_cont and groups:
                groups[-1]["parts"].append(part)
                groups[-1]["marks"].append(s.get("marks"))
            elif not is_cont:
                groups.append({"label": label, "parts": [part], "marks": [s.get("marks")]})
    return groups


async def process_job(job_id: str):
    try:
        job = await load_job(job_id)
        if not job:
            return
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        n = doc.page_count
        await set_fields(job_id, total_pages=n, pages_done=0, error=None)
        jpgs = [page_jpeg(doc, i) for i in range(n)]
        b64s = [base64.b64encode(j).decode() for j in jpgs]

        meta_task = asyncio.create_task(detect_meta(b64s[0], f"{job_id}-meta"))
        page_paths = await asyncio.gather(*[put_object(f"{APP_NAME}/jobs/{job_id}/page_{i}.jpg", j, "image/jpeg") for i, j in enumerate(jpgs)])
        meta = JobMeta(**{k: v for k, v in (await meta_task).items() if k in JobMeta.model_fields})
        canon_meta(meta)
        if job.forced_memo:
            meta.doc_type = "memo"
        is_memo = meta.doc_type == "memo"
        await set_fields(job_id, meta=meta.model_dump(), page_paths=page_paths)

        page_masks = [[] for _ in range(n)]
        sem = asyncio.Semaphore(CONCURRENCY)
        done = {"n": 0}

        async def run(i):
            async with sem:
                segs, excl = await detect_segments(b64s[i], f"{job_id}-p{i + 1}", is_memo)
                page_masks[i] = excl
                done["n"] += 1
                await set_fields(job_id, pages_done=done["n"])
                return segs

        groups = merge_groups(await asyncio.gather(*[run(i) for i in range(n)]))
        cache = {}
        questions = []
        for g in groups:
            first = g["parts"][0].page
            for k in [k for k in cache if k < first]:
                del cache[k]
            questions.append(await build_question(job_id, doc, g["label"], g["parts"], cache, page_masks, sum_marks(g["marks"])))
        doc.close()

        job = await load_job(job_id)
        job.meta, job.page_paths, job.questions, job.page_masks = meta, page_paths, questions, page_masks
        job.status, job.pages_done = "done", n
        renumber(job)
        await save_job(job)
        await try_pair(job)
    except Exception as e:
        logger.exception("Job failed")
        await set_fields(job_id, status="error", error=str(e))


async def worker_loop():
    while True:
        try:
            doc = await db.jobs.find_one_and_update(
                {"status": "queued", "is_deleted": False}, {"$set": {"status": "processing"}}, sort=[("created_at", 1)])
            if not doc:
                await asyncio.sleep(2)
                continue
            await process_job(doc["_id"])
        except Exception:
            logger.exception("Worker error")
            await asyncio.sleep(5)
