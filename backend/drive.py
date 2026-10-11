import os
import re
import io
import asyncio
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
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
from intl import QUALS, qual_for, catalogue_path, skeleton_paths, paper_path as intl_paper_path, YEARS

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


FOLDER_ID = re.compile(r"(?:folders/|id=)([A-Za-z0-9_-]{10,})")


def split_path(path: str) -> List[str]:
    return [p.strip() for p in path.replace("My Drive/", "", 1).split("/") if p.strip()]


def folder_id_from(link: str) -> Optional[str]:
    link = (link or "").strip()
    m = FOLDER_ID.search(link)
    return m.group(1) if m else (link if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link) else None)


async def drive_settings() -> dict:
    doc = await db.settings.find_one({"_id": "drive"}) or {}
    return {"root_id": doc.get("root_id", os.environ.get("DRIVE_ROOT_FOLDER_ID") or None),
            "root_path": doc.get("root_path", os.environ["DRIVE_ROOT_PATH"])}


async def root_path() -> List[str]:
    """Path to the folder holding the Year folders; starts with 'id:<folder>' when a folder link is set."""
    st = await drive_settings()
    return ([f"id:{st['root_id']}"] if st["root_id"] else []) + split_path(st["root_path"])


def show_root(st: dict) -> str:
    return "/".join([f"[linked folder]" if st["root_id"] else "My Drive", *split_path(st["root_path"])])


# ---------- OAuth ----------
@drive_api.get("/connect")
async def connect(user: User = Depends(require_user)):
    state = secrets.token_urlsafe(24)
    flow = _flow(SCOPES)
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="select_account consent",
                                             state=state, login_hint=os.environ["GOOGLE_DRIVE_ACCOUNT"])
    await db.drive_states.insert_one({"_id": state, "user_email": user.email, "code_verifier": flow.code_verifier,
                                      "created_at": datetime.now(timezone.utc)})
    return {"authorization_url": url}


@drive_api.get("/callback")
async def callback(code: Optional[str] = Query(None), state: str = Query(...), error: Optional[str] = Query(None)):
    front = os.environ["FRONTEND_URL"]
    st = await db.drive_states.find_one_and_delete({"_id": state})
    if not st or error or not code:
        return RedirectResponse(f"{front}/?drive=error")
    try:
        flow = _flow(None)
        flow.code_verifier = st.get("code_verifier")  # PKCE: must match the verifier used for the auth URL
        await asyncio.to_thread(flow.fetch_token, code=code)
        c = flow.credentials
    except Exception as e:
        logger.error(f"Drive OAuth failed: {e}")
        return RedirectResponse(f"{front}/?drive=error")
    granted = flow.oauth2session.token.get("scope") or []
    granted = granted.split() if isinstance(granted, str) else list(granted)
    if not set(SCOPES).issubset(granted):
        logger.warning(f"Drive OAuth missing scope, granted: {granted}")
        return RedirectResponse(f"{front}/?drive=scope")
    await db.drive_credentials.update_one({"_id": CRED_ID}, {"$set": {
        "access_token": c.token, "refresh_token": c.refresh_token, "token_uri": c.token_uri, "scopes": granted,
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
    st = await drive_settings()
    return {"connected": bool(doc), "connected_by": doc and doc.get("connected_by"), "root": show_root(st),
            "root_id": st["root_id"], "root_path": st["root_path"],
            "root_link": f"https://drive.google.com/drive/folders/{st['root_id']}" if st["root_id"] else None}


class DriveSettings(BaseModel):
    root_link: str = ""
    root_path: str = ""


@drive_api.put("/settings")
async def save_settings(body: DriveSettings, user: User = Depends(require_user)):
    root_id = folder_id_from(body.root_link) if body.root_link.strip() else None
    if body.root_link.strip() and not root_id:
        raise HTTPException(400, "That doesn't look like a Google Drive folder link")
    parts = split_path(body.root_path)
    if not root_id and not parts:
        raise HTTPException(400, "Give a folder link or a folder path")
    root = ([f"id:{root_id}"] if root_id else []) + parts
    svc = await drive_service()
    if svc:
        try:
            await asyncio.to_thread(DriveWriter(svc, root).folder, root)
        except (RuntimeError, HttpError) as e:
            raise HTTPException(400, f"Folder not reachable with the connected account: {e}"[:300])
    st = {"root_id": root_id, "root_path": "/".join(parts)}
    await db.settings.update_one({"_id": "drive"}, {"$set": {**st, "updated_by": user.email}}, upsert=True)
    return {"root": show_root(st), "checked": bool(svc)}


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
            reason = str(getattr(e, "reason", "")) + str(e.content[:300] if e.content else "")
            if "accessNotConfigured" in reason or "has not been used in project" in reason:
                raise RuntimeError("The Google Drive API is not enabled in your Google Cloud project. Enable it at "
                                   "console.cloud.google.com/apis/library/drive.googleapis.com, wait 2 minutes and try again")
            rate = e.resp.status == 403 and "ateLimit" not in reason
            if e.resp.status in (403, 429, 500, 502, 503) and not rate and attempt < 4:
                import time
                time.sleep(2 ** attempt)
                continue
            raise


class DriveWriter:
    def __init__(self, svc, root: List[str]):
        self.svc, self.cache, self.root = svc, {}, root

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
            if name.startswith("id:"):
                if key not in self.cache:
                    meta = _retry(self.svc.files().get(fileId=name[3:], fields="id,mimeType", supportsAllDrives=True))
                    if meta["mimeType"] != FOLDER:
                        raise RuntimeError("The linked Drive item is not a folder")
                    self.cache[key] = meta["id"]
                parent = self.cache[key]
                continue
            if key not in self.cache:
                fid = self._find(parent, name, True)
                if not fid:
                    if i < len(self.root) and not create_root:
                        raise RuntimeError(f"Drive folder not found: My Drive/{key}")
                    fid = _retry(self.svc.files().create(body={"name": name, "mimeType": FOLDER, "parents": [parent]},
                                                         fields="id", supportsAllDrives=True))["id"]
                self.cache[key] = fid
            parent = self.cache[key]
        return parent

    def put(self, path: List[str], name: str, data: bytes, mime: str, replace: bool) -> bool:
        """PDFs we upload are tagged so the Drive scan never re-imports them."""
        parent = self.folder(path)
        existing = self._find(parent, name, False)
        if existing and not replace:
            return False
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
        if existing:
            _retry(self.svc.files().update(fileId=existing, media_body=media, supportsAllDrives=True))
        else:
            body = {"name": name, "parents": [parent], **({"appProperties": {"papercut": "1"}} if mime == "application/pdf" else {})}
            _retry(self.svc.files().create(body=body, media_body=media, fields="id", supportsAllDrives=True))
        return True


# ---------- set -> Drive layout ----------
def paper_folder(meta, root: List[str]) -> List[str]:
    subj = (meta.subject or "").strip()
    key = next((k for k, al in SUBJECT_ALIASES.items() if subj.lower() in al), None)
    if key == "physical-sciences" and meta.grade in ("7", "8", "9"):
        key = "natural-sciences"
    base = [*root, meta.year or "Unknown Year", f"Grade {meta.grade}" if meta.grade else "Unknown Grade",
            SUBJECT_FOLDERS.get(key, subj or "Unknown Subject")]
    if getattr(meta, "school", ""):
        return base + ["Misc", meta.school.strip()]
    return base + [SESSION_FOLDERS.get(meta.session, "Misc"), PROVINCE_FOLDERS.get(meta.province, meta.province or "DBE")]


CAT_SUBJECT_FOLDERS = {"maths": "Mathematics", "maths-lit": "Mathematical Literacy", "physical-sciences": "Physical Sciences",
                       "natural-sciences": "Natural Sciences", "technical-maths": "Technical Maths", "technical-science": "Technical Science"}


def parent_of(root: List[str]) -> List[str]:
    """Past Paper Database level: the folder above 'CAPS & IEB Past Papers'."""
    return root[:-1] if len(root) > 1 else root


def catalogue_folder(key: str, meta, root: List[str]) -> List[str]:
    q = qual_for(meta)
    if q:
        return catalogue_path(q, parent_of(root))
    grade, subj = key.split("-", 1)
    return parent_of(root) + ["Catalogues", "CAPS & IEB", f"Grade {grade[2:]}", CAT_SUBJECT_FOLDERS.get(subj, subj)]


def plan_base(s: PaperSet, jobs, root: List[str]) -> List[str]:
    """Imported PDFs send their images back to the Drive paper folder they came from."""
    src = next((j.drive_source for j in sorted(jobs, key=lambda j: j.meta.doc_type != "question_paper")
                if j.drive_source and j.drive_source.get("paper_folder_id")), None)
    if src:
        return [f"id:{src['paper_folder_id']}"]
    q = qual_for(s.meta)
    return intl_paper_path(q, s.meta, parent_of(root)) if q else paper_folder(s.meta, root)


def plan_uploads(s: PaperSet, jobs, root: List[str]) -> List[dict]:
    """Every file for this set: {path, name, storage, mime, replace}."""
    base = plan_base(s, jobs, root)
    n = s.meta.paper or "1"
    info = compute_links(jobs)
    by_id = {j.id: j for j in jobs}
    qmap = {(j.id, q.id): q for j in jobs for q in j.questions}
    intl = qual_for(s.meta) is not None
    pdf_dir = ({"question_paper": "Question Paper", "memo": "Memo", "addendum": "Addendum", "errata": "Errata"} if intl else
               {"question_paper": f"Paper_{n}", "memo": f"Memo_Paper_{n}", "addendum": "Addendum", "errata": "Errata"})
    out = [{"path": base + [pdf_dir[j.meta.doc_type]], "name": j.filename, "storage": j.pdf_path, "mime": "application/pdf", "replace": False}
           for j in jobs if j.status == "done" and j.meta.doc_type in pdf_dir and not j.drive_source]
    qp = by_id.get(info["qp_id"])
    if not qp:
        return out
    qroot = base + (["Questions"] if intl else ["Questions", f"Paper_{n}"])
    for q in qp.questions:
        qdir = qroot + [f"Question_{norm_label(q.label) or q.label}"]
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
        root = await root_path()
        items = plan_uploads(s, jobs, root)
        key = catalogue_key(s.meta)
        files = [i for i in items if i["name"]]
        await set_drive(set_id, status="uploading", uploaded=0, skipped=0, total=len(files) + bool(key), error=None)
        w = DriveWriter(svc, root)
        await asyncio.to_thread(w.folder, root)
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
            await asyncio.to_thread(w.put, catalogue_folder(key, s.meta, root), CATALOGUES[key][0], wb,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", True)
            done += 1
        base = plan_base(s, jobs, root)
        folder_id = await asyncio.to_thread(w.folder, base)
        await set_drive(set_id, status="done", uploaded=done, skipped=skipped, error=None,
                        folder_url=f"https://drive.google.com/drive/folders/{folder_id}",
                        folder_path="/".join(p for p in base if not p.startswith("id:")) or "original Drive folder",
                        at=datetime.now(timezone.utc).isoformat())
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


class SkeletonIn(BaseModel):
    qualifications: List[str]
    year_from: int = 2015
    year_to: int = 2027


def _skeleton_list(body: "SkeletonIn", root: List[str]) -> List[List[str]]:
    years = range(max(body.year_from, 2000), min(body.year_to, 2035) + 1)
    paths = []
    for code in body.qualifications:
        q = QUALS.get(code.lower())
        if not q:
            raise HTTPException(400, f"Unknown qualification {code}")
        paths += skeleton_paths(q, years, parent_of(root))
    return paths


@drive_api.get("/skeleton/options")
async def skeleton_options(user: User = Depends(require_user)):
    return {"qualifications": [{"code": q["code"], "label": q["label"], "curriculum": q["curriculum"],
                                "folders_per_year": len(skeleton_paths(q, [2024], []))} for q in QUALS.values()],
            "years": [YEARS.start, YEARS.stop - 1], "status": await db.settings.find_one({"_id": "drive_skeleton"}, {"_id": 0})}


async def run_skeleton(paths: List[List[str]]):
    try:
        w = DriveWriter(await drive_service(), await root_path())
        await db.settings.update_one({"_id": "drive_skeleton"}, {"$set": {"status": "running", "done": 0, "total": len(paths), "error": None}}, upsert=True)
        for i, p in enumerate(paths, 1):
            await asyncio.to_thread(w.folder, p)
            if i % 10 == 0 or i == len(paths):
                await db.settings.update_one({"_id": "drive_skeleton"}, {"$set": {"done": i}})
        await db.settings.update_one({"_id": "drive_skeleton"}, {"$set": {"status": "done"}})
    except Exception as e:
        logger.exception("Drive skeleton failed")
        await db.settings.update_one({"_id": "drive_skeleton"}, {"$set": {"status": "error", "error": str(e)[:300]}})
    finally:
        _tasks.pop("skeleton", None)


@drive_api.post("/skeleton")
async def build_skeleton(body: SkeletonIn, user: User = Depends(require_user)):
    if not await db.drive_credentials.find_one({"_id": CRED_ID}, {"_id": 1}):
        raise HTTPException(400, "Connect Google Drive first")
    if "skeleton" in _tasks:
        raise HTTPException(409, "A folder build is already running")
    paths = _skeleton_list(body, await root_path())
    if not paths:
        raise HTTPException(400, "Pick at least one qualification")
    _tasks["skeleton"] = asyncio.create_task(run_skeleton(paths))
    return {"total": len(paths)}
