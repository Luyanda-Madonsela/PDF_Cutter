import io
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from googleapiclient.http import MediaIoBaseDownload
from core import db, logger
from auth import require_user, User
from drive import drive_service, _retry, FOLDER

import_api = APIRouter(prefix="/api/drive", dependencies=[Depends(require_user)])
PDF_Q = "mimeType='application/pdf' and trashed=false and not appProperties has { key='papercut' and value='1' }"
PAPER_DIRS = re.compile(r"^(Paper_\d+|Memo_Paper_\d+|Addendum|Errata)$", re.I)
STATUS_ID = "drive_import"
_task: Optional[asyncio.Task] = None


async def service_or_400():
    svc = await drive_service()
    if not svc:
        raise HTTPException(400, "Connect Google Drive first")
    return svc


async def imported_ids(ids: List[str]) -> set:
    docs = await db.jobs.find({"is_deleted": False, "drive_source.file_id": {"$in": ids}}, {"drive_source.file_id": 1}).to_list(len(ids) + 1)
    return {d["drive_source"]["file_id"] for d in docs}


def _list(svc, q: str, page_token: Optional[str], size: int):
    return _retry(svc.files().list(q=q, pageSize=size, pageToken=page_token, orderBy="name", corpora="allDrives",
                                   supportsAllDrives=True, includeItemsFromAllDrives=True,
                                   fields="nextPageToken, files(id,name,size,modifiedTime,parents)"))


def _names(svc, ids: List[str]) -> dict:
    out = {}
    for fid in ids:
        try:
            f = _retry(svc.files().get(fileId=fid, fields="id,name,parents", supportsAllDrives=True))
            out[fid] = f
        except Exception:
            out[fid] = {"name": "?", "parents": []}
    return out


@import_api.get("/search")
async def search(q: str = Query(""), page_token: Optional[str] = Query(None), size: int = Query(50, le=200)):
    svc = await service_or_400()
    terms = [t for t in re.split(r"\s+", q.strip()) if t]
    query = PDF_Q + "".join(f" and name contains '{t.replace(chr(92), '').replace(chr(39), chr(92) + chr(39))}'" for t in terms)
    res = await asyncio.to_thread(_list, svc, query, page_token, size)
    files = res.get("files", [])
    parents = await asyncio.to_thread(_names, svc, list({f["parents"][0] for f in files if f.get("parents")}))
    done = await imported_ids([f["id"] for f in files])
    return {"next_page_token": res.get("nextPageToken"), "files": [{
        "id": f["id"], "name": f["name"], "size": int(f.get("size", 0)), "modified": f.get("modifiedTime"),
        "folder": parents.get((f.get("parents") or [None])[0], {}).get("name"), "imported": f["id"] in done} for f in files]}


def _download(svc, fid: str) -> bytes:
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid, supportsAllDrives=True), chunksize=8 * 1024 * 1024)
    finished = False
    while not finished:
        _, finished = dl.next_chunk(num_retries=3)
    return buf.getvalue()


def _source(svc, fid: str) -> dict:
    """Where the PDF lives: images go back to the paper folder (parent of Paper_N / Memo_Paper_N / Addendum / Errata)."""
    f = _retry(svc.files().get(fileId=fid, fields="id,name,parents", supportsAllDrives=True))
    parent_id = (f.get("parents") or [None])[0]
    paper_folder = None
    if parent_id:
        p = _retry(svc.files().get(fileId=parent_id, fields="id,name,parents,mimeType", supportsAllDrives=True))
        if PAPER_DIRS.match(p["name"]) and p.get("parents"):
            paper_folder = p["parents"][0]
    return {"name": f["name"], "file_id": fid, "parent_id": parent_id, "paper_folder_id": paper_folder}


async def import_one(svc, fid: str) -> bool:
    from routes import new_job  # lazy: routes is the API module
    if await imported_ids([fid]):
        return False
    src = await asyncio.to_thread(_source, svc, fid)
    data = await asyncio.to_thread(_download, svc, fid)
    pymupdf.open(stream=data, filetype="pdf").close()
    name = src["name"] if src["name"].lower().endswith(".pdf") else src["name"] + ".pdf"
    job = await new_job(name, data)
    await db.jobs.update_one({"_id": job.id}, {"$set": {"drive_source": {k: src[k] for k in ("file_id", "parent_id", "paper_folder_id")}}})
    return True


async def _status(**fields):
    await db.settings.update_one({"_id": STATUS_ID}, {"$set": fields}, upsert=True)


async def run_import(ids: Optional[List[str]], limit: int):
    global _task
    try:
        svc = await drive_service()
        if ids is None:
            await _status(status="scanning", found=0)
            ids, token = [], None
            while len(ids) < limit:
                res = await asyncio.to_thread(_list, svc, PDF_Q, token, 1000)
                batch = [f["id"] for f in res.get("files", [])]
                seen = await imported_ids(batch)
                ids += [b for b in batch if b not in seen]
                await _status(found=len(ids))
                token = res.get("nextPageToken")
                if not token:
                    break
            ids = ids[:limit]
        await _status(status="importing", total=len(ids), done=0, imported=0, failed=0, errors=[])
        done = imported = failed = 0
        errors = []
        for fid in ids:
            try:
                imported += await import_one(svc, fid)
            except Exception as e:
                failed += 1
                errors = (errors + [f"{fid}: {str(e)[:120]}"])[-10:]
                logger.warning(f"Drive import {fid} failed: {e}")
            done += 1
            await _status(done=done, imported=imported, failed=failed, errors=errors)
        await _status(status="done", finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.exception("Drive import failed")
        await _status(status="error", error=str(e)[:300])
    finally:
        _task = None


def start(ids: Optional[List[str]], limit: int):
    global _task
    if _task:
        raise HTTPException(409, "A Drive import is already running")
    _task = asyncio.create_task(run_import(ids, limit))


class ImportBody(BaseModel):
    file_ids: List[str]


class ScanBody(BaseModel):
    limit: int = 200


@import_api.post("/import")
async def import_files(body: ImportBody):
    await service_or_400()
    if not body.file_ids:
        raise HTTPException(400, "Pick at least one PDF")
    await _status(status="queued", total=len(body.file_ids), done=0, imported=0, failed=0, errors=[], error=None, kind="selected")
    start(body.file_ids, len(body.file_ids))
    return {"ok": True}


@import_api.post("/scan")
async def scan(body: ScanBody):
    await service_or_400()
    limit = max(1, min(body.limit, 1000))
    await _status(status="queued", total=0, done=0, imported=0, failed=0, errors=[], error=None, found=0, kind="scan", limit=limit)
    start(None, limit)
    return {"ok": True}


@import_api.get("/import-status")
async def import_status():
    doc = await db.settings.find_one({"_id": STATUS_ID}, {"_id": 0}) or {"status": "idle"}
    if doc.get("status") in ("queued", "scanning", "importing") and not _task:
        doc["status"] = "interrupted"
    return doc
