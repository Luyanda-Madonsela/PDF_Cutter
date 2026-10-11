import os
import time
import asyncio
import logging
import requests
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
LLM_KEY = os.environ['EMERGENT_LLM_KEY']
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "papercut"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("papercut")

_storage_key = None


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _storage_call(method: str, path: str, headers: Optional[dict] = None, **kw):
    force = False
    resp = None
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
    if resp is None:
        raise RuntimeError("Storage unreachable")
    resp.raise_for_status()
    return resp


async def put_object(path: str, data: bytes, content_type: str) -> str:
    resp = await asyncio.to_thread(_storage_call, "PUT", path, data=data, headers={"Content-Type": content_type})
    return resp.json()["path"]


async def get_object(path: str) -> bytes:
    resp = await asyncio.to_thread(_storage_call, "GET", path)
    return resp.content
