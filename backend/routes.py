import io
import asyncio
import zipfile
import re
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from auth import require_user
from fastapi.responses import Response, StreamingResponse
import pymupdf
from core import db, put_object, get_object, APP_NAME
from models import Job, JobMeta, PaperSet, QuestionUpdate, QuestionSplit, EraseDecision, MemoLinkUpdate, QuestionAnnotations, DOC_TYPES
from catalogue import CATALOGUES, catalogue_key, locate, build_workbook
from jobs import (load_job, load_set, set_jobs, save_job, set_fields, renumber, refresh_set, compute_links,
                  rebuild_question, canon_meta, update_set_meta, sum_marks, norm_label,
                  erase_proposals, ERASE_FLAG, DIFF_FLAG, match_topic, stop_job, rate_set, hardest, RATING, BULK, rate_all,
                  ensure_school_test_number, next_school_test_number, school_test_scope, split_parts)
from ai import LEVELS
from syllabus import rename

api = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
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
    out["catalogue"] = locate(s.meta)
    out["erase_pending"] = sum(1 for j in jobs for q in j.questions if q.erase_status == "pending")
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


def has_manual_edits(job: Job) -> bool:
    return any(q.reviewed or q.erase_status in ("applied", "rejected") or q.erase_manual for q in job.questions)


async def done_qp_jobs():
    sets = [PaperSet.from_mongo(d) for d in await db.sets.find({"is_deleted": False, "status": "done"}).to_list(20000)]
    out = []
    for s in sets:
        qp = next((j for j in await set_jobs(s.id) if j.meta.doc_type == "question_paper" and j.status == "done"), None)
        if qp:
            out.append((s, qp))
    return out


async def recrop(s: PaperSet, qp: Job):
    await set_fields(qp.id, status="ready", questions=[], pages_done=0, error=None)
    await db.sets.update_one({"_id": s.id}, {"$set": {"drive": None}})  # finished re-crop re-uploads to Drive
    await refresh_set(s.id)


@api.get("/sets/recrop-preview")
async def recrop_preview():
    pairs = await done_qp_jobs()
    return {"sets": len(pairs), "edited": sum(has_manual_edits(qp) for _, qp in pairs)}


@api.post("/sets/recrop-all")
async def recrop_all():
    pairs = await done_qp_jobs()
    for s, qp in pairs:
        await recrop(s, qp)
    return {"queued": len(pairs)}


@api.post("/sets/{set_id}/recrop")
async def recrop_set(set_id: str):
    pair = next((p for p in await done_qp_jobs() if p[0].id == set_id), None)
    if not pair:
        raise HTTPException(400, "Only finished paper sets with a question paper can be re-cropped")
    await recrop(*pair)
    return await set_detail(await load_set(set_id))


@api.get("/sets/rate-difficulty-all")
async def rate_all_status():
    return BULK


@api.post("/sets/rate-difficulty-all")
async def rate_all_sets():
    if BULK["status"] == "running":
        raise HTTPException(400, "Difficulty rating is already running")
    pairs = [(s.id, qp.id) for s, qp in await done_qp_jobs() if qp.questions]
    BULK.update(status="running", done=0, total=len(pairs), error=None)
    RATING["_bulk"] = asyncio.create_task(rate_all(pairs))
    return BULK


@api.post("/sets/{set_id}/rate-difficulty")
async def rate_set_difficulty(set_id: str):
    s = await set_or_404(set_id)
    qp = next((j for j in await set_jobs(set_id) if j.meta.doc_type == "question_paper" and j.status == "done" and j.questions), None)
    if not qp:
        raise HTTPException(400, "This set has no finished question paper to rate")
    if set_id in RATING:
        raise HTTPException(400, "Difficulty rating is already running for this set")
    await db.sets.update_one({"_id": set_id}, {"$set": {"rating": {"status": "running", "done": 0, "total": len(qp.questions), "error": None}}})
    RATING[set_id] = asyncio.create_task(rate_set(set_id, qp.id))
    return await set_detail(await load_set(set_id))


@api.get("/sets/{set_id}")
async def get_set(set_id: str):
    return await set_detail(await set_or_404(set_id))


@api.patch("/sets/{set_id}/meta")
async def patch_set_meta(set_id: str, meta: JobMeta):
    s = await set_or_404(set_id)
    old_scope = school_test_scope(s.meta)
    meta = canon_meta(meta)
    await update_set_meta(s, meta)
    if s.meta.school and (s.school_test_number is None or school_test_scope(s.meta) != old_scope):
        s.school_test_number = await next_school_test_number(s.meta)
        await db.sets.update_one({"_id": s.id}, {"$set": {"school_test_number": s.school_test_number}})
    elif not s.meta.school and s.school_test_number is not None:
        s.school_test_number = None
        await db.sets.update_one({"_id": s.id}, {"$set": {"school_test_number": None}})
    if s.meta.school and s.school_test_number is None:
        await ensure_school_test_number(s)
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


# ---------- catalogues ----------
async def catalogue_entries() -> dict:
    out = {k: [] for k in CATALOGUES}
    sets = await db.sets.find({"is_deleted": False, "status": "done"}).to_list(20000)
    sets = [PaperSet.from_mongo(d) for d in sets]
    sets.sort(key=lambda s: (s.meta.language.lower() == "english", s.created_at))  # English wins a shared row
    for s in sets:
        key = catalogue_key(s.meta)
        if not key or not locate(s.meta).get("found"):
            continue
        jobs = await set_jobs(s.id)
        qp = next((j for j in jobs if j.meta.doc_type == "question_paper" and j.status == "done"), None)
        if not qp:
            continue
        errata = sorted({norm_label(q.label) for j in jobs if j.meta.doc_type == "errata" for q in j.questions if norm_label(q.label)[:1].isdigit()},
                        key=lambda x: [int(p) for p in x.split(".")])
        out[key].append({"meta": s.meta, "questions": [{"label": norm_label(q.label), "topic": q.topic, "difficulty": q.difficulty} for q in qp.questions], "errata": errata})
    return out


@api.post("/catalogues/refresh-topics")
async def refresh_topics():
    """Move stored question topics onto the current catalogue column names."""
    changed = cleared = 0
    sets = [PaperSet.from_mongo(d) for d in await db.sets.find({"is_deleted": False}).to_list(20000)]
    for s in sets:
        key = catalogue_key(s.meta)
        topics = locate(s.meta).get("topics", []) if key else []
        for job in await set_jobs(s.id):
            if job.meta.doc_type != "question_paper":
                continue
            dirty = False
            for q in job.questions:
                if not q.topic or q.topic in topics:
                    continue
                new = match_topic(rename(key, q.topic), topics)
                changed, cleared = changed + bool(new), cleared + (not new)
                q.topic = new
                if not new and "Topic not set" not in q.flags:
                    q.flags.append("Topic not set")
                dirty = True
            if dirty:
                await save_job(job)
    return {"updated": changed, "cleared": cleared}


@api.get("/catalogues")
async def list_catalogues():
    entries = await catalogue_entries()
    return [{"key": k, "name": f.replace(".xlsx", ""), "filename": f, "grade": g, "papers_filled": len(entries[k])} for k, (f, g) in CATALOGUES.items()]


@api.get("/catalogues/{key}/download")
async def download_catalogue(key: str):
    if key not in CATALOGUES:
        raise HTTPException(404, "Catalogue not found")
    entries = await catalogue_entries()
    data = await asyncio.to_thread(build_workbook, key, entries[key])
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{CATALOGUES[key][0]}"'})


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


@api.post("/jobs/{job_id}/stop")
async def stop_document(job_id: str):
    job = await job_or_404(job_id)
    if job.status not in ("queued", "classifying", "ready", "processing", "paused"):
        raise HTTPException(400, "This document is not being worked on")
    if not stop_job(job_id):  # not running yet: just take it out of the queue
        await set_fields(job_id, status="stopped", pages_done=0, error="Stopped by you. Press Retry to start again")
    for _ in range(20):
        if (await load_job(job_id)).status == "stopped":
            break
        await asyncio.sleep(0.25)
    if job.set_id:
        await refresh_set(job.set_id)
    return {"ok": True}


@api.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    job = await job_or_404(job_id)
    if job.status not in ("error", "stopped"):
        raise HTTPException(400, "Only failed or stopped documents can be retried")
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


async def set_qp_difficulty(job: Job, q, difficulty):
    """Memo/addendum/errata edits change the matching question-paper question; refresh_set copies it back."""
    qp = next((j for j in await set_jobs(job.set_id) if j.meta.doc_type == "question_paper" and j.status == "done"), None) if job.set_id else None
    n = norm_label(q.label)
    hits = [x for x in qp.questions if norm_label(x.label) == n] if qp else []
    hits = hits or ([x for x in qp.questions if norm_label(x.label).startswith(n + ".")] if qp else [])
    if not hits:
        raise HTTPException(400, f"No Q{q.label} in the question paper to rate")
    for x in hits:
        x.difficulty = difficulty
        x.flags = [f for f in x.flags if f != DIFF_FLAG]
    s = await load_set(job.set_id)
    renumber(qp, s.base_name)
    await save_job(qp)


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
    if body.label is not None and body.label.strip() and body.label.strip() != q.label:
        _, linked = await linked_targets(job, qid)
        for _, lq in linked:
            lq.label = body.label.strip()
        await save_linked([j for j, _ in linked], job.set_id)
        q.label = body.label.strip()
    if body.marks is not None:
        q.marks = body.marks
        q.flags = [f for f in q.flags if f != "Marks not found"]
    if body.clear_marks:
        q.marks = None
    if body.topic is not None:
        q.topic = body.topic or None
        q.flags = [f for f in q.flags if f != "Topic not set"]
    if body.difficulty is not None:
        if body.difficulty and body.difficulty not in LEVELS:
            raise HTTPException(400, "Difficulty must be Easy, Medium or Hard")
        q.difficulty = body.difficulty or None
        q.flags = [f for f in q.flags if f != DIFF_FLAG]
        if job.meta.doc_type != "question_paper":
            await set_qp_difficulty(job, q, q.difficulty)
    if body.parts is not None:
        if not body.parts:
            raise HTTPException(400, "At least one crop region required")
        for p in body.parts:
            if p.page < 0 or p.page >= job.total_pages or not (0 <= p.y0 < p.y1 <= 1000):
                raise HTTPException(400, "Invalid crop region")
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        job.questions[idx] = await rebuild_question(job, doc, q.label, body.parts, q.marks, q.flags, q.id, q.reviewed, q.topic,
                                                    q.erase_applied, q.erase_status, q.erase_manual, q.crop_history + [q.parts], q.difficulty,
                                                    q.annotations, q.related_labels, q.erase_white, q.memo_links)
        doc.close()
    return await edit_and_return(job, job.set_id)


@api.post("/jobs/{job_id}/questions/{qid}/split")
async def split_question(job_id: str, qid: str, body: QuestionSplit):
    job = await job_or_404(job_id)
    require_done(job)
    if job.meta.doc_type != "question_paper":
        raise HTTPException(400, "Only question-paper questions can be split")
    idx = find_idx(job, qid)
    question = job.questions[idx]
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "A label is required for the new question")
    if norm_label(label) == norm_label(question.label):
        raise HTTPException(400, f"Question label {label} is already in use")
    used_labels = {
        norm_label(existing_label)
        for existing in job.questions
        if existing.id != qid
        for existing_label in (existing.related_labels or [existing.label])
    }
    if norm_label(label) in used_labels:
        raise HTTPException(400, f"Question label {label} is already in use")
    parts = body.parts if body.parts is not None else question.parts
    if not parts:
        raise HTTPException(400, "At least one crop region required")
    for part in parts:
        if part.page < 0 or part.page >= job.total_pages or not (0 <= part.y0 < part.y1 <= 1000):
            raise HTTPException(400, "Invalid crop region")
    try:
        first_parts, second_parts = split_parts(parts, body.page, body.y)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

    original_labels = question.related_labels or [question.label]
    original_related_labels = [
        existing_label for existing_label in original_labels
        if norm_label(existing_label) != norm_label(label)
    ]
    new_question_flags = list(dict.fromkeys(question.flags + ["Marks not found"]))
    doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
    try:
        original = await rebuild_question(
            job, doc, question.label, first_parts, question.marks, question.flags, question.id,
            reviewed=False, topic=question.topic, erase_applied=question.erase_applied,
            erase_status=question.erase_status, erase_manual=question.erase_manual,
            crop_history=[], difficulty=question.difficulty,
            annotations=question.annotations, related_labels=original_related_labels,
            erase_white=question.erase_white, memo_links=question.memo_links,
        )
        new_question = await rebuild_question(
            job, doc, label, second_parts, None, new_question_flags, "",
            reviewed=False, topic=question.topic, erase_applied=question.erase_applied,
            erase_status=question.erase_status, erase_manual=question.erase_manual,
            difficulty=question.difficulty, related_labels=[label], erase_white=question.erase_white,
        )
    finally:
        doc.close()
    job.questions[idx] = original
    job.questions.insert(idx + 1, new_question)
    return await edit_and_return(job, job.set_id)


@api.put("/jobs/{job_id}/questions/{qid}/annotations")
async def update_question_annotations(job_id: str, qid: str, body: QuestionAnnotations):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    if len(body.annotations) > 500:
        raise HTTPException(400, "At most 500 annotations are allowed per image")
    for annotation in body.annotations:
        if not isinstance(annotation, dict) or annotation.get("type") not in ("path", "text"):
            raise HTTPException(400, "Annotation type must be path or text")
        color = annotation.get("color", "#e11d48")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise HTTPException(400, "Annotation color must be a six-digit hex color")
        if annotation["type"] == "text":
            if not isinstance(annotation.get("text"), str) or len(annotation["text"]) > 300:
                raise HTTPException(400, "Annotation text must be 300 characters or fewer")
            points = [[annotation.get("x"), annotation.get("y")]]
        else:
            points = annotation.get("points")
            if not isinstance(points, list) or len(points) > 5000:
                raise HTTPException(400, "Path annotation must contain at most 5000 points")
        for point in points:
            if (not isinstance(point, list) or len(point) != 2
                    or any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in point)):
                raise HTTPException(400, "Annotation coordinates must be normalized between 0 and 1")
    job.questions[idx].annotations = body.annotations
    await save_job(job)
    return await set_detail(await load_set(job.set_id)) if job.set_id else job.model_dump(exclude=JOB_EXCLUDE)


@api.post("/jobs/{job_id}/questions/{qid}/undo-crop")
async def undo_crop(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    q = job.questions[idx]
    if not q.crop_history:
        raise HTTPException(400, "No earlier crop to go back to")
    doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
    job.questions[idx] = await rebuild_question(job, doc, q.label, q.crop_history[-1], q.marks, q.flags, q.id, q.reviewed, q.topic,
                                                q.erase_applied, q.erase_status, q.erase_manual, q.crop_history[:-1], q.difficulty,
                                                q.annotations, q.related_labels, q.erase_white, q.memo_links)
    doc.close()
    return await edit_and_return(job, job.set_id)


@api.get("/jobs/{job_id}/questions/{qid}/erase")
async def get_erase_proposals(job_id: str, qid: str):
    job = await job_or_404(job_id)
    q = job.questions[find_idx(job, qid)]
    return {"status": q.erase_status, "proposals": erase_proposals(job, q.parts), "applied": q.erase_applied,
            "manual": q.erase_manual, "white": q.erase_white, "pages": sorted({p.page for p in q.parts})}


@api.put("/jobs/{job_id}/questions/{qid}/memo-links")
async def update_memo_links(job_id: str, qid: str, body: MemoLinkUpdate):
    job = await job_or_404(job_id)
    require_done(job)
    if job.meta.doc_type != "question_paper" or not job.set_id:
        raise HTTPException(400, "Memo answers can only be linked to a question-paper question in a set")
    idx = find_idx(job, qid)
    memo_job = next((j for j in await set_jobs(job.set_id) if j.meta.doc_type == "memo" and j.status == "done"), None)
    available = {question.id for question in memo_job.questions} if memo_job else set()
    requested = list(dict.fromkeys(body.memo_qids))
    if any(memo_qid not in available for memo_qid in requested):
        raise HTTPException(400, "A selected memo answer does not belong to a completed memo in this set")
    job.questions[idx].memo_links = requested
    return await edit_and_return(job, job.set_id)


def valid_manual(q, boxes: List[List[int]]) -> List[List[int]]:
    out = []
    for b in boxes:
        if len(b) != 5:
            raise HTTPException(400, "Manual erase box must be [page, ymin, xmin, ymax, xmax]")
        page, y0, x0, y1, x1 = (int(v) for v in b)
        if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
            raise HTTPException(400, "Manual erase box out of range")
        if not any(p.page == page and y1 > p.y0 and y0 < p.y1 for p in q.parts):
            raise HTTPException(400, "Manual erase box must overlap the question's crop")
        if [page, y0, x0, y1, x1] not in out:
            out.append([page, y0, x0, y1, x1])
    return out


async def apply_erase(job: Job, doc, idx: int, boxes: List[List[int]], manual: List[List[int]] = None,
                      white: List[List[int]] = None):
    q = job.questions[idx]
    allowed = erase_proposals(job, q.parts)
    manual = valid_manual(q, manual or [])
    white = valid_manual(q, white or [])
    chosen = [b for b in boxes if b in allowed] + [b for b in manual if b not in allowed] + [b for b in white if b not in allowed]
    flags = [f for f in q.flags if f != ERASE_FLAG]
    job.questions[idx] = await rebuild_question(job, doc, q.label, q.parts, q.marks, flags, q.id, q.reviewed, q.topic,
                                                chosen, "applied" if chosen else "rejected", manual, q.crop_history, q.difficulty,
                                                q.annotations, q.related_labels, white, q.memo_links)


@api.post("/jobs/{job_id}/questions/{qid}/erase")
async def decide_erase(job_id: str, qid: str, body: EraseDecision):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
    await apply_erase(job, doc, idx, body.boxes, body.manual, body.white)
    doc.close()
    return await edit_and_return(job, job.set_id)


@api.post("/sets/{set_id}/erase-approve-all")
async def approve_all_erases(set_id: str):
    await set_or_404(set_id)
    for job in await set_jobs(set_id):
        pending = [i for i, q in enumerate(job.questions) if q.erase_status == "pending"]
        if job.status != "done" or not pending:
            continue
        doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
        for i in pending:
            await apply_erase(job, doc, i, erase_proposals(job, job.questions[i].parts),
                              job.questions[i].erase_manual, job.questions[i].erase_white)
        doc.close()
        await edit_and_return(job, set_id)
    return await set_detail(await load_set(set_id))


@api.post("/sets/{set_id}/review-all")
async def review_all_questions(set_id: str):
    await set_or_404(set_id)
    reviewed = 0
    for job in await set_jobs(set_id):
        if job.meta.doc_type != "question_paper" or job.status != "done":
            continue
        changed = False
        for question in job.questions:
            if not question.reviewed:
                question.reviewed = True
                reviewed += 1
                changed = True
        if changed:
            await save_job(job)
    await refresh_set(set_id)
    result = await set_detail(await load_set(set_id))
    result["reviewed_questions"] = reviewed
    return result


@api.post("/jobs/{job_id}/questions/{qid}/review")
async def mark_reviewed(job_id: str, qid: str):
    job = await job_or_404(job_id)
    job.questions[find_idx(job, qid)].reviewed = True
    return await edit_and_return(job, job.set_id)


# ---------- linked images (memo / addendum / errata follow the question paper) ----------
async def linked_targets(job: Job, qid: str):
    """For a question-paper question: the set's other jobs and the linked images whose label matches it exactly."""
    if not job.set_id or job.meta.doc_type != "question_paper":
        return {}, []
    jobs = {j.id: j for j in await set_jobs(job.set_id) if j.id != job.id}
    info = compute_links([job, *jobs.values()])
    if info["qp_id"] != job.id or qid not in info["links"]:
        return jobs, []
    q = next(x for x in job.questions if x.id == qid)
    link = info["links"][qid]
    memo_refs = link.get("memos") or ([link["memo"]] if link["memo"] else [])
    memo_ref_ids = {(r["job_id"], r["qid"]) for r in memo_refs}
    refs = memo_refs + link["addenda"] + link["errata"]
    out = []
    for r in refs:
        j = jobs[r["job_id"]]
        lq = next((x for x in j.questions if x.id == r["qid"]), None)
        labels = {norm_label(label) for label in (q.related_labels or [q.label])}
        is_memo = (r["job_id"], r["qid"]) in memo_ref_ids
        if lq and (is_memo or norm_label(lq.label) in labels) and (j, lq) not in out:
            out.append((j, lq))
    return jobs, out


async def save_linked(changed, set_id):
    s = await load_set(set_id)
    for j in {j.id: j for j in changed}.values():
        renumber(j, s.base_name if s else j.base_name)
        await save_job(j)


async def merge_questions(job: Job, question_ids: List[str], memo_links=None):
    question_id_set = set(question_ids)
    selected = [
        (index, question) for index, question in enumerate(job.questions)
        if question.id in question_id_set
    ]
    if not selected:
        return None
    a = selected[0][1]
    if len(selected) == 1:
        return a

    parts = []
    previous_source_index = None
    for source_index, question in selected:
        for part in question.parts:
            adjacent_source = previous_source_index in (source_index, source_index - 1)
            if (parts and adjacent_source and parts[-1].page == part.page
                    and part.y0 <= parts[-1].y1 + 30):
                parts[-1].y1 = max(parts[-1].y1, part.y1)
            else:
                parts.append(part.model_copy())
            previous_source_index = source_index
    selected_questions = [question for _, question in selected]
    flags = list(dict.fromkeys(flag for question in selected_questions for flag in question.flags))
    doc = pymupdf.open(stream=await get_object(job.pdf_path), filetype="pdf")
    statuses = [question.erase_status for question in selected_questions]
    status = "pending" if "pending" in statuses else next((value for value in statuses if value != "none"), "none")
    try:
        merged = await rebuild_question(
            job, doc, a.label, parts, sum_marks([question.marks for question in selected_questions]), flags, a.id,
            topic=next((question.topic for question in selected_questions if question.topic), None),
            erase_applied=[box for question in selected_questions for box in question.erase_applied],
            erase_status=status,
            erase_manual=[box for question in selected_questions for box in question.erase_manual],
            difficulty=hardest([question.difficulty for question in selected_questions]),
            annotations=[annotation for question in selected_questions for annotation in question.annotations],
            related_labels=list(dict.fromkeys(
                label for question in selected_questions for label in (question.related_labels or [question.label])
            )),
            erase_white=[box for question in selected_questions for box in question.erase_white],
            memo_links=memo_links if memo_links is not None else list(dict.fromkeys(
                memo_id for question in selected_questions for memo_id in question.memo_links
            )),
        )
    finally:
        doc.close()
    first_idx = next(i for i, question in enumerate(job.questions) if question.id == a.id)
    job.questions[first_idx] = merged
    job.questions = [
        question for question in job.questions
        if question.id == a.id or question.id not in question_id_set
    ]
    return merged


async def merge_at(job: Job, idx: int, memo_links=None):
    return await merge_questions(job, [job.questions[idx].id, job.questions[idx + 1].id], memo_links)


@api.post("/jobs/{job_id}/questions/{qid}/merge-next")
async def merge_next(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    idx = find_idx(job, qid)
    if idx + 1 >= len(job.questions):
        raise HTTPException(400, "No next question to merge with")
    a, b = job.questions[idx], job.questions[idx + 1]
    _, la = await linked_targets(job, a.id)
    _, lb = await linked_targets(job, b.id)
    changed = []
    memo_groups = {}
    for linked_job, linked_question in la + lb:
        if linked_job.meta.doc_type != "memo":
            continue
        group = memo_groups.setdefault(linked_job.id, (linked_job, []))
        if linked_question.id not in group[1]:
            group[1].append(linked_question.id)

    merged_memo_ids = []
    remapped_memo_ids = {}
    for linked_job, linked_ids in memo_groups.values():
        linked_id_set = set(linked_ids)
        ordered_ids = [question.id for question in linked_job.questions if question.id in linked_id_set]
        if not ordered_ids:
            continue
        merged_question = await merge_questions(linked_job, ordered_ids)
        merged_memo_ids.append(merged_question.id)
        remapped_memo_ids.update({linked_id: merged_question.id for linked_id in ordered_ids})
        if len(ordered_ids) > 1:
            changed.append(linked_job)

    for j, bq in lb:
        if j.meta.doc_type == "memo":
            continue
        aq = next((x for jj, x in la if jj.id == j.id), None)
        ii = next(i for i, x in enumerate(j.questions) if x.id == bq.id)
        if aq and ii > 0 and j.questions[ii - 1].id == aq.id:
            await merge_at(j, ii - 1)
        elif not aq:
            bq.label = a.label
        else:
            continue
        changed.append(j)
    memo_links = None
    if a.memo_links or b.memo_links:
        memo_links = list(dict.fromkeys(
            remapped_memo_ids.get(memo_id, memo_id) for memo_id in a.memo_links + b.memo_links
        ))
        memo_links.extend(memo_id for memo_id in merged_memo_ids if memo_id not in memo_links)
    await merge_at(job, idx, memo_links)
    await save_linked(changed, job.set_id)
    return await edit_and_return(job, job.set_id)


@api.delete("/jobs/{job_id}/questions/{qid}")
async def delete_question(job_id: str, qid: str):
    job = await job_or_404(job_id)
    require_done(job)
    find_idx(job, qid)
    _, linked = await linked_targets(job, qid)
    for j, lq in linked:
        j.questions = [x for x in j.questions if x.id != lq.id]
    await save_linked([j for j, _ in linked], job.set_id)
    job.questions = [q for q in job.questions if q.id != qid]
    return await edit_and_return(job, job.set_id)
