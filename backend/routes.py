import io
import re
import uuid
import asyncio
import zipfile
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
import pymupdf
from core import db, put_object, get_object, APP_NAME
from models import Job, JobMeta, QuestionUpdate
from jobs import load_job, save_job, renumber, try_pair, unpair, build_question, norm_label

api = APIRouter(prefix="/api")
SUMMARY_EXCLUDE = {"questions": 0, "page_paths": 0}


async def job_or_404(job_id: str) -> Job:
    job = await load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def require_done(job: Job):
    if job.status != "done":
        raise HTTPException(400, "Job not finished")


async def job_detail(job: Job) -> dict:
    out = job.model_dump(exclude={"page_paths"})
    out["paired"] = None
    out["pair_map"] = {}
    if job.paired_job_id:
        partner = await load_job(job.paired_job_id)
        if partner:
            out["paired"] = {"job_id": partner.id, "filename": partner.filename, "status": partner.status,
                             "doc_type": partner.meta.doc_type, "base_name": partner.base_name,
                             "pages_done": partner.pages_done, "total_pages": partner.total_pages}
            by_label = {}
            for pq in partner.questions:
                by_label.setdefault(norm_label(pq.label), pq.id)
            out["pair_map"] = {q.id: by_label[norm_label(q.label)] for q in job.questions if norm_label(q.label) in by_label}
    return out


@api.get("/")
async def root():
    return {"message": "PaperCut API"}


@api.post("/jobs")
async def create_job(file: UploadFile = File(...), pair_with: Optional[str] = Query(None)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "Invalid or corrupted PDF")
    job = Job(filename=file.filename)
    if pair_with:
        target = await job_or_404(pair_with)
        await unpair(target)
        job.forced_memo = True
        job.paired_job_id = target.id
    job.pdf_path = await put_object(f"{APP_NAME}/pdfs/{job.id}.pdf", data, "application/pdf")
    await db.jobs.insert_one(job.to_mongo())
    if pair_with:
        await db.jobs.update_one({"_id": pair_with}, {"$set": {"paired_job_id": job.id}})
    return job.model_dump(exclude={"page_paths"})


@api.get("/jobs")
async def list_jobs():
    docs = await db.jobs.find({"is_deleted": False}, SUMMARY_EXCLUDE).sort("created_at", -1).to_list(2000)
    counts = {s: 0 for s in ("queued", "processing", "done", "error")}
    async for c in db.jobs.aggregate([{"$match": {"is_deleted": False}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[c["_id"]] = c["n"]
    return {"jobs": [Job.from_mongo(d).model_dump(exclude={"page_paths", "questions"}) for d in docs], "counts": counts}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return await job_detail(await job_or_404(job_id))


@api.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    job = await job_or_404(job_id)
    if job.status != "error":
        raise HTTPException(400, "Only failed jobs can be retried")
    await db.jobs.update_one({"_id": job_id}, {"$set": {"status": "queued", "error": None, "pages_done": 0, "questions": []}})
    return {"ok": True}


@api.patch("/jobs/{job_id}/meta")
async def update_meta(job_id: str, meta: JobMeta):
    job = await job_or_404(job_id)
    require_done(job)
    type_changed = job.meta.doc_type != meta.doc_type
    job.meta = meta
    renumber(job)
    await save_job(job)
    if type_changed or not job.paired_job_id:
        await unpair(job)
        job.paired_job_id = None
        await try_pair(job)
    return await job_detail(await job_or_404(job_id))


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
    return Response(content=await get_object(job.page_paths[page]), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


async def open_pdf(job: Job):
    return pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")


@api.put("/jobs/{job_id}/questions/{qid}")
async def update_question(job_id: str, qid: str, body: QuestionUpdate):
    job = await job_or_404(job_id)
    require_done(job)
    idx = next((i for i, q in enumerate(job.questions) if q.id == qid), None)
    if idx is None:
        raise HTTPException(404, "Question not found")
    q = job.questions[idx]
    if body.label is not None and body.label.strip():
        q.label = body.label.strip()
    if body.parts is not None:
        if not body.parts:
            raise HTTPException(400, "At least one crop region required")
        for p in body.parts:
            if p.page < 0 or p.page >= job.total_pages or not (0 <= p.y0 < p.y1 <= 1000):
                raise HTTPException(400, "Invalid crop region")
        doc = await open_pdf(job)
        job.questions[idx] = await build_question(job.id, doc, q.label, body.parts, {}, qid=q.id)
        doc.close()
    renumber(job)
    await save_job(job)
    return await job_detail(job)


@api.post("/jobs/{job_id}/questions/{qid}/merge-next")
async def merge_next(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    idx = next((i for i, q in enumerate(job.questions) if q.id == qid), None)
    if idx is None or idx + 1 >= len(job.questions):
        raise HTTPException(400, "No next question to merge with")
    a, b = job.questions[idx], job.questions[idx + 1]
    doc = await open_pdf(job)
    parts = []
    for p in a.parts + b.parts:
        if parts and parts[-1].page == p.page and p.y0 <= parts[-1].y1 + 30:
            parts[-1].y1 = max(parts[-1].y1, p.y1)
        else:
            parts.append(p.model_copy())
    job.questions[idx] = await build_question(job.id, doc, a.label, parts, {}, qid=a.id)
    doc.close()
    del job.questions[idx + 1]
    renumber(job)
    await save_job(job)
    return await job_detail(job)


@api.delete("/jobs/{job_id}/questions/{qid}")
async def delete_question(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    job.questions = [q for q in job.questions if q.id != qid]
    renumber(job)
    await save_job(job)
    return await job_detail(job)


@api.get("/jobs/{job_id}/zip")
async def download_zip(job_id: str):
    job = await job_or_404(job_id)
    require_done(job)
    folder = job.base_name or re.sub(r"[^A-Za-z0-9_\-]", "_", job.filename)
    entries = [(f"{folder}/{q.filename}", q.storage_path) for q in job.questions]
    partner = await load_job(job.paired_job_id) if job.paired_job_id else None
    if partner and partner.status == "done" and job.meta.doc_type != "memo":
        by_label = {}
        for pq in partner.questions:
            by_label.setdefault(norm_label(pq.label), pq)
        used = set()
        for q in job.questions:
            pq = by_label.get(norm_label(q.label))
            if pq:
                used.add(pq.id)
                entries.append((f"{folder}/{q.filename[:-4]}_MEMO.png", pq.storage_path))
        entries += [(f"{folder}/memo_unmatched/{pq.filename}", pq.storage_path) for pq in partner.questions if pq.id not in used]
    blobs = await asyncio.gather(*[get_object(p) for _, p in entries])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for (name, _), b in zip(entries, blobs):
            z.writestr(name, b)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'})


@api.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    job = await job_or_404(job_id)
    await unpair(job)
    await db.jobs.update_one({"_id": job_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}
