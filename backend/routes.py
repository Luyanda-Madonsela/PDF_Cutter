import io
import asyncio
import zipfile
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
import pymupdf
from core import db, put_object, get_object, APP_NAME
from models import Job, JobMeta, PaperSet, QuestionUpdate, DOC_TYPES
from jobs import (load_job, load_set, set_jobs, save_job, set_fields, renumber, refresh_set, compute_links,
                  rebuild_question, canon_meta, update_set_meta, sum_marks)

api = APIRouter(prefix="/api")
JOB_EXCLUDE = {"page_paths", "page_masks"}


async def job_or_404(job_id: str) -> Job:
    job = await load_job(job_id)
    if not job:
        raise HTTPException(404, "Document not found")
    return job


async def set_or_404(set_id: str) -> PaperSet:
    s = await load_set(set_id)
    if not s:
        raise HTTPException(404, "Paper set not found")
    return s


def require_done(job: Job):
    if job.status != "done":
        raise HTTPException(400, "Document not finished processing")


async def read_pdf(file: UploadFile) -> bytes:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, f"{file.filename}: only PDF files are supported")
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, f"{file.filename}: invalid or corrupted PDF")
    return data


async def new_job(filename: str, data: bytes, set_id: Optional[str] = None, doc_type: Optional[str] = None) -> Job:
    job = Job(filename=filename, set_id=set_id, forced_type=doc_type)
    if doc_type:
        job.meta.doc_type = doc_type
    job.pdf_path = await put_object(f"{APP_NAME}/pdfs/{job.id}.pdf", data, "application/pdf")
    await db.jobs.insert_one(job.to_mongo())
    return job


async def set_detail(s: PaperSet) -> dict:
    jobs = await set_jobs(s.id)
    out = s.model_dump()
    out["documents"] = [j.model_dump(exclude=JOB_EXCLUDE) for j in jobs]
    out.update(compute_links(jobs))
    return out


@api.get("/")
async def root():
    return {"message": "PaperCut API"}


# ---------- uploads ----------
@api.post("/sets")
async def create_set(question_paper: UploadFile = File(...), memo: UploadFile = File(...),
                     addenda: List[UploadFile] = File(default=[]), errata: List[UploadFile] = File(default=[])):
    files = [(question_paper, "question_paper"), (memo, "memo")] + [(f, "addendum") for f in addenda if f.filename] + [(f, "errata") for f in errata if f.filename]
    payload = [(f.filename, await read_pdf(f), t) for f, t in files]
    s = PaperSet(mode="single", status="processing")
    await db.sets.insert_one(s.to_mongo())
    for name, data, t in payload:
        await new_job(name, data, s.id, t)
    await refresh_set(s.id)
    return await set_detail(await load_set(s.id))


@api.post("/jobs")
async def upload_document(file: UploadFile = File(...), set_id: Optional[str] = Query(None), doc_type: Optional[str] = Query(None)):
    if doc_type and doc_type not in DOC_TYPES:
        raise HTTPException(400, "Invalid document type")
    if set_id:
        await set_or_404(set_id)
    job = await new_job(file.filename, await read_pdf(file), set_id, doc_type)
    if set_id:
        await refresh_set(set_id)
    return job.model_dump(exclude=JOB_EXCLUDE)


# ---------- sets ----------
@api.get("/sets")
async def list_sets():
    docs = await db.sets.find({"is_deleted": False}).sort("created_at", -1).to_list(3000)
    counts = {s: 0 for s in ("needs_memo", "needs_paper", "processing", "done", "error")}
    async for c in db.sets.aggregate([{"$match": {"is_deleted": False}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[c["_id"]] = c["n"]
    counts["sorting"] = await db.jobs.count_documents({"is_deleted": False, "set_id": None, "status": {"$in": ["queued", "classifying"]}})
    counts["flagged"] = await db.sets.count_documents({"is_deleted": False, "flagged": {"$gt": 0}})
    return {"sets": [PaperSet.from_mongo(d).model_dump() for d in docs], "counts": counts}


@api.get("/sets/{set_id}")
async def get_set(set_id: str):
    return await set_detail(await set_or_404(set_id))


@api.patch("/sets/{set_id}/meta")
async def patch_set_meta(set_id: str, meta: JobMeta):
    s = await set_or_404(set_id)
    await update_set_meta(s, canon_meta(meta))
    for j in await set_jobs(set_id):
        renumber(j, s.base_name)
        await save_job(j)
    return await set_detail(await load_set(set_id))


@api.delete("/sets/{set_id}")
async def delete_set(set_id: str):
    await set_or_404(set_id)
    await db.sets.update_one({"_id": set_id}, {"$set": {"is_deleted": True}})
    await db.jobs.update_many({"set_id": set_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


@api.get("/sets/{set_id}/zip")
async def download_set_zip(set_id: str):
    s = await set_or_404(set_id)
    jobs = {j.id: j for j in await set_jobs(set_id)}
    info = compute_links(list(jobs.values()))
    if not info["qp_id"]:
        raise HTTPException(400, "Question paper not finished")
    qp = jobs[info["qp_id"]]
    folder = s.base_name or "paper"
    qmap = {(j.id, q.id): q for j in jobs.values() for q in j.questions}
    entries = []
    for q in qp.questions:
        stem = q.filename[:-4]
        entries.append((f"{folder}/{q.filename}", q.storage_path))
        link = info["links"][q.id]
        if link["memo"]:
            entries.append((f"{folder}/{stem}_MEMO.png", qmap[(link["memo"]["job_id"], link["memo"]["qid"])].storage_path))
        for key, tag in (("addenda", "ADDENDUM"), ("errata", "ERRATA")):
            for i, ref in enumerate(link[key], start=1):
                entries.append((f"{folder}/{stem}_{tag}{i if len(link[key]) > 1 else ''}.png", qmap[(ref["job_id"], ref["qid"])].storage_path))
    for key, sub in (("general", "addendum_general"), ("unlinked", "unlinked"), ("memo_unmatched", "memo_unmatched")):
        for ref in info["extras"][key]:
            mq = qmap[(ref["job_id"], ref["qid"])]
            entries.append((f"{folder}/{sub}/{mq.filename}", mq.storage_path))
    blobs = await asyncio.gather(*[get_object(p) for _, p in entries])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for (name, _), b in zip(entries, blobs):
            z.writestr(name, b)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'})


# ---------- documents ----------
@api.get("/jobs/{job_id}/images/{qid}")
async def get_image(job_id: str, qid: str):
    job = await job_or_404(job_id)
    q = next((q for q in job.questions if q.id == qid), None)
    if not q:
        raise HTTPException(404, "Image not found")
    return Response(content=await get_object(q.storage_path), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@api.get("/jobs/{job_id}/pages/{page}")
async def get_page(job_id: str, page: int):
    job = await job_or_404(job_id)
    if page < 0 or page >= len(job.page_paths):
        raise HTTPException(404, "Page not found")
    return Response(content=await get_object(job.page_paths[page]), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@api.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    job = await job_or_404(job_id)
    if job.status != "error":
        raise HTTPException(400, "Only failed documents can be retried")
    await set_fields(job_id, status="queued", error=None, pages_done=0, questions=[])
    if job.set_id:
        await refresh_set(job.set_id)
    return {"ok": True}


@api.delete("/jobs/{job_id}")
async def delete_document(job_id: str):
    job = await job_or_404(job_id)
    await set_fields(job_id, is_deleted=True)
    if job.set_id:
        await refresh_set(job.set_id)
    return {"ok": True}


async def edit_and_return(job: Job, set_id: Optional[str]):
    s = await load_set(set_id)
    renumber(job, s.base_name if s else job.base_name)
    await save_job(job)
    if s:
        await refresh_set(s.id)
        return await set_detail(await load_set(s.id))
    return job.model_dump(exclude=JOB_EXCLUDE)


def find_idx(job: Job, qid: str) -> int:
    idx = next((i for i, q in enumerate(job.questions) if q.id == qid), None)
    if idx is None:
        raise HTTPException(404, "Question not found")
    return idx


@api.put("/jobs/{job_id}/questions/{qid}")
async def update_question(job_id: str, qid: str, body: QuestionUpdate):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    q = job.questions[idx]
    if body.label is not None and body.label.strip():
        q.label = body.label.strip()
    if body.marks is not None:
        q.marks = body.marks
        q.flags = [f for f in q.flags if f != "Marks not found"]
    if body.clear_marks:
        q.marks = None
    if body.parts is not None:
        if not body.parts:
            raise HTTPException(400, "At least one crop region required")
        for p in body.parts:
            if p.page < 0 or p.page >= job.total_pages or not (0 <= p.y0 < p.y1 <= 1000):
                raise HTTPException(400, "Invalid crop region")
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        job.questions[idx] = await rebuild_question(job, doc, q.label, body.parts, q.marks, q.flags, q.id, q.reviewed)
        doc.close()
    return await edit_and_return(job, job.set_id)


@api.post("/jobs/{job_id}/questions/{qid}/review")
async def mark_reviewed(job_id: str, qid: str):
    job = await job_or_404(job_id)
    job.questions[find_idx(job, qid)].reviewed = True
    return await edit_and_return(job, job.set_id)


@api.post("/jobs/{job_id}/questions/{qid}/merge-next")
async def merge_next(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    if idx + 1 >= len(job.questions):
        raise HTTPException(400, "No next question to merge with")
    a, b = job.questions[idx], job.questions[idx + 1]
    parts = []
    for p in a.parts + b.parts:
        if parts and parts[-1].page == p.page and p.y0 <= parts[-1].y1 + 30:  # touching regions on the same page
            parts[-1].y1 = max(parts[-1].y1, p.y1)
        else:
            parts.append(p.model_copy())
    flags = [f for f in dict.fromkeys(a.flags + b.flags)]
    doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
    job.questions[idx] = await rebuild_question(job, doc, a.label, parts, sum_marks([a.marks, b.marks]), flags, a.id)
    doc.close()
    del job.questions[idx + 1]
    return await edit_and_return(job, job.set_id)


@api.delete("/jobs/{job_id}/questions/{qid}")
async def delete_question(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    job.questions = [q for q in job.questions if q.id != qid]
    return await edit_and_return(job, job.set_id)
