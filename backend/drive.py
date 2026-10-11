import os
import io
import asyncio
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from core import db, get_object, logger
from auth import require_user, User
from models import PaperSet
from jobs import load_set, set_jobs, compute_links, norm_label
from catalogue import CATALOGUES, SUBJECT_ALIASES, catalogue_key, build_workbook

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
CRED_ID = "shared"
SUBJECT_FOLDERS = {"maths": "Mathematics", "maths-lit": "Mathematical Literacy", "physical-sciences": "Physical Sciences",
                   "natural-sciences": "Natural Sciences", "technical-maths": "Technical Mathematics",
                   "technical-science": "Technical Sciences"}
SESSION_FOLDERS = {"Feb/Mar": "Feb-Mar", "May/Jun": "May-Jun", "Sep": "Sept", "Nov": "Nov", "Exemplar": "Misc"}
PROVINCE_FOLDERS = {"National": "DBE", "LP": "LIM"}

drive_api = APIRouter(prefix="/api/drive")
_tasks: Dict[str, asyncio.Task] = {}


def _client_config():
    return {"web": {"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [os.environ["GOOGLE_DRIVE_REDIRECT_URI"]]}}


def _flow(scopes):
    return Flow.from_client_config(_client_config(), scopes=scopes, redirect_uri=os.environ["GOOGLE_DRIVE_REDIRECT_URI"])


def root_path() -> List[str]:
    return [p.strip() for p in os.environ["DRIVE_ROOT_PATH"].split("/") if p.strip()]


# ---------- OAuth ----------
@drive_api.get("/connect")
async def connect(user: User = Depends(require_user)):
    state = secrets.token_urlsafe(24)
    await db.drive_states.insert_one({"_id": state, "user_email": user.email, "created_at": datetime.now(timezone.utc)})
    url, _ = _flow(SCOPES).authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
    return {"authorization_url": url}


@drive_api.get("/callback")
async def callback(code: Optional[str] = Query(None), state: str = Query(...), error: Optional[str] = Query(None)):
    front = os.environ["FRONTEND_URL"]
    st = await db.drive_states.find_one_and_delete({"_id": state})
    if not st or error or not code:
        return RedirectResponse(f"{front}/?drive=error")
    try:
        flow = _flow(None)
        await asyncio.to_thread(flow.fetch_token, code=code)
        c = flow.credentials
    except Exception as e:
        logger.error(f"Drive OAuth failed: {e}")
        return RedirectResponse(f"{front}/?drive=error")
    if not set(SCOPES).issubset(set(c.scopes or [])):
        return RedirectResponse(f"{front}/?drive=scope")
    await db.drive_credentials.update_one({"_id": CRED_ID}, {"$set": {
        "access_token": c.token, "refresh_token": c.refresh_token, "token_uri": c.token_uri, "scopes": list(c.scopes or []),
        "expiry": c.expiry.replace(tzinfo=timezone.utc).isoformat() if c.expiry else None,
        "connected_by": st["user_email"], "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return RedirectResponse(f"{front}/?drive=connected")


async def drive_service():
    doc = await db.drive_credentials.find_one({"_id": CRED_ID})
    if not doc:
        return None
    creds = Credentials(token=doc["access_token"], refresh_token=doc.get("refresh_token"), token_uri=doc["token_uri"],
                        client_id=os.environ["GOOGLE_CLIENT_ID"], client_secret=os.environ["GOOGLE_CLIENT_SECRET"], scopes=doc["scopes"])
    if doc.get("expiry"):
        creds.expiry = datetime.fromisoformat(doc["expiry"]).replace(tzinfo=None)
    if not creds.valid and creds.refresh_token:
        await asyncio.to_thread(creds.refresh, GoogleRequest())
        await db.drive_credentials.update_one({"_id": CRED_ID}, {"$set": {
            "access_token": creds.token, "expiry": creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None}})
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@drive_api.get("/status")
async def status(user: User = Depends(require_user)):
    doc = await db.drive_credentials.find_one({"_id": CRED_ID}, {"_id": 0, "connected_by": 1, "updated_at": 1})
    return {"connected": bool(doc), "connected_by": doc and doc.get("connected_by"), "root": "/".join(["My Drive", *root_path()])}


@drive_api.post("/disconnect")
async def disconnect(user: User = Depends(require_user)):
    await db.drive_credentials.delete_one({"_id": CRED_ID})
    return {"ok": True}


# ---------- Drive helpers (sync; run in a thread) ----------
def _q(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def _retry(req):
    for attempt in range(5):
        try:
            return req.execute()
        except HttpError as e:
            if e.resp.status in (403, 429, 500, 502, 503) and attempt < 4:
                import time
                time.sleep(2 ** attempt)
                continue
            raise


class DriveWriter:
    def __init__(self, svc):
        self.svc, self.cache = svc, {}

    def _find(self, parent: str, name: str, folder: bool):
        mime = f"(mimeType='{FOLDER}' or mimeType='{SHORTCUT}')" if folder else f"mimeType!='{FOLDER}'"
        res = _retry(self.svc.files().list(q=f"name='{_q(name)}' and '{parent}' in parents and trashed=false and {mime}",
                                           fields="files(id,mimeType,shortcutDetails)", pageSize=10,
                                           supportsAllDrives=True, includeItemsFromAllDrives=True))
        for f in res.get("files", []):
            if f["mimeType"] == SHORTCUT:
                if folder and f.get("shortcutDetails", {}).get("targetMimeType") == FOLDER:
                    return f["shortcutDetails"]["targetId"]
                continue
            return f["id"]
        return None

    def folder(self, path: List[str], create_root: bool = False) -> str:
        parent, walked = "root", []
        for i, name in enumerate(path):
            walked.append(name)
            key = "/".join(walked)
            if key not in self.cache:
                fid = self._find(parent, name, True)
                if not fid:
                    if i < len(root_path()) and not create_root:
                        raise RuntimeError(f"Drive folder not found: My Drive/{key}")
                    fid = _retry(self.svc.files().create(body={"name": name, "mimeType": FOLDER, "parents": [parent]},
                                                         fields="id", supportsAllDrives=True))["id"]
                self.cache[key] = fid
            parent = self.cache[key]
        return parent

    def put(self, path: List[str], name: str, data: bytes, mime: str, replace: bool) -> bool:
        parent = self.folder(path)
        existing = self._find(parent, name, False)
        if existing and not replace:
            return False
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
        if existing:
            _retry(self.svc.files().update(fileId=existing, media_body=media, supportsAllDrives=True))
        else:
            _retry(self.svc.files().create(body={"name": name, "parents": [parent]}, media_body=media, fields="id", supportsAllDrives=True))
        return True


# ---------- set -> Drive layout ----------
def paper_folder(meta) -> List[str]:
    subj = (meta.subject or "").strip()
    key = next((k for k, al in SUBJECT_ALIASES.items() if subj.lower() in al), None)
    if key == "physical-sciences" and meta.grade in ("7", "8", "9"):
        key = "natural-sciences"
    return [*root_path(), meta.year or "Unknown Year", f"Grade {meta.grade}" if meta.grade else "Unknown Grade",
            SUBJECT_FOLDERS.get(key, subj or "Unknown Subject"), SESSION_FOLDERS.get(meta.session, "Misc"),
            PROVINCE_FOLDERS.get(meta.province, meta.province or "DBE")]


def plan_uploads(s: PaperSet, jobs) -> List[dict]:
    """Every file for this set: {path, name, storage, mime, replace}."""
    base = paper_folder(s.meta)
    n = s.meta.paper or "1"
    info = compute_links(jobs)
    by_id = {j.id: j for j in jobs}
    qmap = {(j.id, q.id): q for j in jobs for q in j.questions}
    pdf_dir = {"question_paper": f"Paper_{n}", "memo": f"Memo_Paper_{n}", "addendum": "Addendum", "errata": "Errata"}
    out = [{"path": base + [pdf_dir[j.meta.doc_type]], "name": j.filename, "storage": j.pdf_path, "mime": "application/pdf", "replace": False}
           for j in jobs if j.status == "done" and j.meta.doc_type in pdf_dir]
    qp = by_id.get(info["qp_id"])
    if not qp:
        return out
    qroot = base + ["Questions", f"Paper_{n}"]
    for q in qp.questions:
        main = norm_label(q.label).split(".")[0] or q.label
        qdir = qroot + [f"Question_{main}"]
        out.append({"path": qdir + ["Question"], "name": q.filename, "storage": q.storage_path, "mime": "image/png", "replace": True})
        link = info["links"][q.id]
        refs = ([("Memo", link["memo"])] if link["memo"] else []) + [("Addendum", r) for r in link["addenda"]] + [("Errata", r) for r in link["errata"]]
        for sub, r in refs:
            lq = qmap[(r["job_id"], r["qid"])]
            out.append({"path": qdir + [sub], "name": lq.filename, "storage": lq.storage_path, "mime": "image/png", "replace": True})
        for sub in ("Hints", "Video"):
            out.append({"path": qdir + [sub], "name": None})
    for key, sub in (("general", ["General", "Addendum"]), ("unlinked", ["Unlinked"]), ("memo_unmatched", ["Unmatched", "Memo"])):
        for r in info["extras"][key]:
            mq = qmap[(r["job_id"], r["qid"])]
            out.append({"path": qroot + sub, "name": mq.filename, "storage": mq.storage_path, "mime": "image/png", "replace": True})
    return out


async def set_drive(set_id: str, **fields):
    await db.sets.update_one({"_id": set_id}, {"$set": {f"drive.{k}": v for k, v in fields.items()}})


async def run_send(set_id: str):
    from routes import catalogue_entries  # lazy: routes is the API module
    try:
        svc = await drive_service()
        if not svc:
            raise RuntimeError("Google Drive is not connected")
        s = await load_set(set_id)
        jobs = await set_jobs(set_id)
        items = plan_uploads(s, jobs)
        key = catalogue_key(s.meta)
        files = [i for i in items if i["name"]]
        await set_drive(set_id, status="uploading", uploaded=0, skipped=0, total=len(files) + bool(key), error=None)
        w = DriveWriter(svc)
        await asyncio.to_thread(w.folder, root_path())
        done = skipped = 0
        for it in items:
            if not it["name"]:
                await asyncio.to_thread(w.folder, it["path"])
                continue
            data = await get_object(it["storage"])
            wrote = await asyncio.to_thread(w.put, it["path"], it["name"], data, it["mime"], it["replace"])
            done, skipped = done + 1, skipped + (not wrote)
            if done % 5 == 0:
                await set_drive(set_id, uploaded=done, skipped=skipped)
        if key:
            entries = await catalogue_entries()
            wb = await asyncio.to_thread(build_workbook, key, entries[key])
            await asyncio.to_thread(w.put, [*root_path(), "Catalogues"], CATALOGUES[key][0], wb,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", True)
            done += 1
        folder_id = await asyncio.to_thread(w.folder, paper_folder(s.meta))
        await set_drive(set_id, status="done", uploaded=done, skipped=skipped, error=None,
                        folder_url=f"https://drive.google.com/drive/folders/{folder_id}",
                        folder_path="/".join(["My Drive", *paper_folder(s.meta)]), at=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.exception("Drive upload failed")
        await set_drive(set_id, status="error", error=str(e)[:300])
    finally:
        _tasks.pop(set_id, None)


def start_send(set_id: str):
    if set_id in _tasks:
        return
    _tasks[set_id] = asyncio.create_task(run_send(set_id))


async def auto_send(set_id: str):
    if await db.drive_credentials.find_one({"_id": CRED_ID}, {"_id": 1}):
        await db.sets.update_one({"_id": set_id}, {"$set": {"drive": {"status": "queued", "auto": True}}})
        start_send(set_id)


@drive_api.post("/sets/{set_id}/send")
async def send_set(set_id: str, user: User = Depends(require_user)):
    s = await load_set(set_id)
    if not s:
        raise HTTPException(404, "Paper set not found")
    if s.status != "done":
        raise HTTPException(400, "Paper set is not finished yet")
    if not await db.drive_credentials.find_one({"_id": CRED_ID}, {"_id": 1}):
        raise HTTPException(400, "Connect Google Drive first")
    await db.sets.update_one({"_id": set_id}, {"$set": {"drive": {"status": "queued"}}})
    start_send(set_id)
    return {"ok": True}
