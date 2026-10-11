from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import re
import json
import base64
import asyncio
import logging
import zipfile
import uuid
import time
import requests
from pathlib import Path
from typing import List, Optional, Annotated, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
import pymupdf
from PIL import Image, ImageOps
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
LLM_KEY = os.environ['EMERGENT_LLM_KEY']
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "papercut"
storage_key = None

RENDER_ZOOM = 2.5  # ~180 dpi crops
AI_ZOOM = 1.4
CONCURRENCY = 6

app = FastAPI()
api = APIRouter(prefix="/api")
logger = logging.getLogger("papercut")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": LLM_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def _storage_call(method: str, path: str, headers: Optional[dict] = None, **kw):
    force = False
    for attempt in range(5):
        try:
            resp = requests.request(method, f"{STORAGE_URL}/objects/{path}",
                                    headers={"X-Storage-Key": init_storage(force), **(headers or {})}, timeout=120, **kw)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404 and not force:
            force = True
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        break
    resp.raise_for_status()
    return resp


def put_object(path: str, data: bytes, content_type: str) -> str:
    return _storage_call("PUT", path, data=data, headers={"Content-Type": content_type}).json()["path"]


def get_object(path: str) -> bytes:
    return _storage_call("GET", path).content


PyObjectId = Annotated[str, BeforeValidator(str)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")

    def to_mongo(self) -> dict:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)


class QuestionImage(BaseModel):
    order: int
    label: str
    filename: str
    storage_path: str
    pages: List[int]
    width: int
    height: int


class Job(BaseDocument):
    filename: str
    pdf_path: str = ""
    is_deleted: bool = False
    status: str = "queued"  # queued | processing | done | error
    total_pages: int = 0
    pages_done: int = 0
    error: Optional[str] = None
    questions: List[QuestionImage] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def job_out(job: Job) -> dict:
    return job.model_dump(by_alias=False)


PROMPT = """You are analysing ONE page image from a South African high school exam past paper (NSC/IEB/DBE, any subject, English or Afrikaans).
Find where every question/sub-question region starts and stops vertically on this page.

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
{"segments":[{"label":"1.1","y_start":120,"y_end":340}]}"""


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"No JSON in response: {text[:200]}")
    return json.loads(m.group(0))


async def detect_segments(img_b64: str, job_id: str, page_no: int) -> list:
    last_err = None
    for attempt in range(3):
        try:
            chat = LlmChat(
                api_key=LLM_KEY,
                session_id=f"{job_id}-p{page_no}-{attempt}",
                system_message="You are a precise document layout analyser. Output only valid JSON.",
            ).with_model("gemini", "gemini-3-flash-preview")
            text = ""
            async for ev in chat.stream_message(UserMessage(text=PROMPT, file_contents=[ImageContent(image_base64=img_b64)])):
                if isinstance(ev, TextDelta):
                    text += ev.content
                elif isinstance(ev, StreamDone):
                    break
            segs = parse_json(text).get("segments", [])
            out = []
            for s in segs:
                y0, y1 = int(s["y_start"]), int(s["y_end"])
                y0, y1 = max(0, min(1000, y0)), max(0, min(1000, y1))
                if y1 - y0 > 5:
                    out.append({"label": str(s.get("label", "CONTINUED")).strip(), "y0": y0, "y1": y1})
            return sorted(out, key=lambda s: s["y0"])
        except Exception as e:
            last_err = e
            logger.warning(f"Page {page_no} attempt {attempt} failed: {e}")
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI failed on page {page_no}: {last_err}")


def trim_vertical(img: Image.Image, pad: int = 12) -> Image.Image:
    gray = ImageOps.invert(img.convert("L"))
    bbox = gray.point(lambda p: 255 if p > 40 else 0).getbbox()
    if not bbox:
        return img
    top = max(0, bbox[1] - pad)
    bottom = min(img.height, bbox[3] + pad)
    return img.crop((0, top, img.width, bottom))


def stitch(parts: List[Image.Image]) -> Image.Image:
    w = max(p.width for p in parts)
    gap = 16
    h = sum(p.height for p in parts) + gap * (len(parts) - 1)
    out = Image.new("RGB", (w, h), "white")
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9.\-]", "_", label)


async def update_job(job_id: str, **fields):
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})


async def process_job(job_id: str, pdf_bytes: bytes):
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        n = doc.page_count
        await update_job(job_id, status="processing", total_pages=n)
        ai_imgs = []
        for i in range(n):
            pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(AI_ZOOM, AI_ZOOM))
            ai_imgs.append(base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode())

        sem = asyncio.Semaphore(CONCURRENCY)
        done = {"n": 0}

        async def run(i):
            async with sem:
                segs = await detect_segments(ai_imgs[i], job_id, i + 1)
                done["n"] += 1
                await update_job(job_id, pages_done=done["n"])
                return segs

        page_segs = await asyncio.gather(*[run(i) for i in range(n)])

        # Merge segments across pages in reading order
        groups = []  # {"label", "parts": [(page, y0, y1)]}
        for p, segs in enumerate(page_segs):
            for s in segs:
                label = s["label"]
                is_cont = label.upper() in ("CONTINUED", "CONT", "") or (groups and groups[-1]["label"] == label)
                if is_cont and groups:
                    groups[-1]["parts"].append((p, s["y0"], s["y1"]))
                elif not is_cont:
                    groups.append({"label": label, "parts": [(p, s["y0"], s["y1"])]})

        page_cache = {}

        def page_img(p):
            if p not in page_cache:
                pix = doc[p].get_pixmap(matrix=pymupdf.Matrix(RENDER_ZOOM, RENDER_ZOOM))
                page_cache[p] = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            return page_cache[p]

        questions = []
        seen = {}
        for idx, g in enumerate(groups, start=1):
            first_page = g["parts"][0][0]
            for k in [k for k in page_cache if k < first_page]:
                del page_cache[k]
            parts = []
            for p, y0, y1 in g["parts"]:
                im = page_img(p)
                crop = im.crop((0, int(im.height * y0 / 1000), im.width, int(im.height * y1 / 1000)))
                parts.append(trim_vertical(crop))
            final = stitch(parts)
            label = safe_label(g["label"])
            seen[label] = seen.get(label, 0) + 1
            suffix = f"_{seen[label]}" if seen[label] > 1 else ""
            fname = f"{idx:03d}_Q{label}{suffix}.png"
            buf = io.BytesIO()
            final.save(buf, format="PNG", optimize=True)
            spath = await asyncio.to_thread(put_object, f"{APP_NAME}/jobs/{job_id}/{uuid.uuid4()}.png", buf.getvalue(), "image/png")
            questions.append(QuestionImage(order=idx, label=g["label"], filename=fname, storage_path=spath,
                                           pages=sorted({p + 1 for p, _, _ in g["parts"]}),
                                           width=final.width, height=final.height).model_dump())
        doc.close()
        await update_job(job_id, status="done", questions=questions, pages_done=n)
    except Exception as e:
        logger.exception("Job failed")
        await update_job(job_id, status="error", error=str(e))


async def get_job_or_404(job_id: str) -> Job:
    doc = await db.jobs.find_one({"_id": job_id, "is_deleted": False})
    if not doc:
        raise HTTPException(404, "Job not found")
    return Job.from_mongo(doc)


@api.get("/")
async def root():
    return {"message": "PaperCut API"}


@api.post("/jobs")
async def create_job(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "Invalid or corrupted PDF")
    job = Job(filename=file.filename)
    job.pdf_path = await asyncio.to_thread(put_object, f"{APP_NAME}/pdfs/{job.id}.pdf", data, "application/pdf")
    await db.jobs.insert_one(job.to_mongo())
    asyncio.create_task(process_job(job.id, data))
    return job_out(job)


@api.get("/jobs")
async def list_jobs():
    docs = await db.jobs.find({"is_deleted": False}, {"questions": 0}).sort("created_at", -1).to_list(200)
    return [job_out(Job.from_mongo(d)) for d in docs]


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return job_out(await get_job_or_404(job_id))


@api.get("/jobs/{job_id}/images/{filename}")
async def get_image(job_id: str, filename: str):
    job = await get_job_or_404(job_id)
    q = next((q for q in job.questions if q.filename == filename), None)
    if not q:
        raise HTTPException(404, "Image not found")
    data = await asyncio.to_thread(get_object, q.storage_path)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


def zip_name(job: Job) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", Path(job.filename).stem)


@api.get("/jobs/{job_id}/zip")
async def download_zip(job_id: str):
    job = await get_job_or_404(job_id)
    if job.status != "done":
        raise HTTPException(400, "Job not finished")
    folder = zip_name(job)
    blobs = await asyncio.gather(*[asyncio.to_thread(get_object, q.storage_path) for q in job.questions])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for q, b in zip(job.questions, blobs):
            z.writestr(f"{folder}/{q.filename}", b)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'})


@api.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    await get_job_or_404(job_id)
    await db.jobs.update_one({"_id": job_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def mark_stale():
    try:
        await asyncio.to_thread(init_storage)
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await db.jobs.update_many({"status": {"$in": ["queued", "processing"]}},
                              {"$set": {"status": "error", "error": "Server restarted during processing. Please re-upload."}})


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
