import os
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bson import json_util
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

MONGO_URL = (os.environ.get("MONGO_URL") or "mongodb://localhost:27017").strip() or "mongodb://localhost:27017"
DB_NAME = (os.environ.get("DB_NAME") or "papercut").strip() or "papercut"

_PLACEHOLDER_LLM_KEYS = {"demo-dev-key", "demo", "changeme", "placeholder", "your-api-key", "your_key_here", "test-key", "invalid", "none", "null"}


def _clean_llm_key(value: Optional[str]) -> str:
    if value is None:
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    return "" if cleaned.lower() in _PLACEHOLDER_LLM_KEYS else cleaned


LLM_KEY = _clean_llm_key(os.environ.get("EMERGENT_LLM_KEY"))
OPENROUTER_KEY = _clean_llm_key(os.environ.get("OPENROUTER_API_KEY"))
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip()
APP_NAME = "papercut"
LOCAL_STORAGE_ROOT = ROOT_DIR / "local_storage"
LOCAL_DB_SNAPSHOT = LOCAL_STORAGE_ROOT / "papercut" / "metadata.json"
_LOCAL_PERSISTED_COLLECTIONS = {"jobs", "sets", "settings"}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("papercut")

_use_mock_mongo = os.environ.get("USE_REAL_MONGO", "0") != "1"


class _AsyncCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self

    async def to_list(self, length: int):
        return list(self._cursor[:length])

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._cursor)
        except StopIteration:
            raise StopAsyncIteration


class _AsyncCollection:
    def __init__(self, collection, on_write=None):
        self._collection = collection
        self._on_write = on_write

    def _persist(self, result):
        if self._on_write:
            self._on_write()
        return result

    def __getattr__(self, name):
        attr = getattr(self._collection, name)

        if name in {"find", "aggregate", "distinct", "list_indexes"}:
            def wrapper(*args, **kwargs):
                return _AsyncCursor(attr(*args, **kwargs))
            return wrapper

        if callable(attr):
            async def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                if name in {"bulk_write", "find_one_and_delete", "find_one_and_replace", "find_one_and_update"}:
                    return self._persist(result)
                return result
            return wrapper

        return attr

    def find(self, *args, **kwargs):
        return _AsyncCursor(self._collection.find(*args, **kwargs))

    async def find_one(self, *args, **kwargs):
        return self._collection.find_one(*args, **kwargs)

    async def insert_one(self, *args, **kwargs):
        return self._persist(self._collection.insert_one(*args, **kwargs))

    async def insert_many(self, *args, **kwargs):
        return self._persist(self._collection.insert_many(*args, **kwargs))

    async def update_one(self, *args, **kwargs):
        return self._persist(self._collection.update_one(*args, **kwargs))

    async def update_many(self, *args, **kwargs):
        return self._persist(self._collection.update_many(*args, **kwargs))

    async def replace_one(self, *args, **kwargs):
        return self._persist(self._collection.replace_one(*args, **kwargs))

    async def delete_one(self, *args, **kwargs):
        return self._persist(self._collection.delete_one(*args, **kwargs))

    async def delete_many(self, *args, **kwargs):
        return self._persist(self._collection.delete_many(*args, **kwargs))

    async def create_index(self, *args, **kwargs):
        return self._collection.create_index(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        return _AsyncCursor(self._collection.aggregate(*args, **kwargs))

    async def count_documents(self, *args, **kwargs):
        return self._collection.count_documents(*args, **kwargs)

    async def distinct(self, *args, **kwargs):
        return self._collection.distinct(*args, **kwargs)


class _AsyncDatabase:
    def __init__(self, db, on_write=None):
        self._db = db
        self._on_write = on_write

    def __getattr__(self, name):
        return _AsyncCollection(getattr(self._db, name), self._collection_writer(name))

    def __getitem__(self, name):
        return _AsyncCollection(self._db[name], self._collection_writer(name))

    def _collection_writer(self, name):
        return self._on_write if name in _LOCAL_PERSISTED_COLLECTIONS else None

    def list_collection_names(self):
        return self._db.list_collection_names()


class _AsyncMongoClient:
    def __init__(self, client, on_write=None):
        self._client = client
        self._on_write = on_write

    def __getitem__(self, name):
        return _AsyncDatabase(self._client[name], self._on_write)

    def close(self):
        self._client.close()


def _save_local_snapshot(raw_client, snapshot_path: Path = LOCAL_DB_SNAPSHOT):
    state = {
        name: list(raw_client[DB_NAME][name].find())
        for name in sorted(_LOCAL_PERSISTED_COLLECTIONS)
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = snapshot_path.with_suffix(".tmp")
    temporary_path.write_text(json_util.dumps(state), encoding="utf-8")
    os.replace(temporary_path, snapshot_path)


def _restore_local_snapshot(raw_client, snapshot_path: Path = LOCAL_DB_SNAPSHOT):
    if not snapshot_path.exists():
        return
    state = json_util.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError(f"Invalid local database snapshot: {snapshot_path}")
    for name in _LOCAL_PERSISTED_COLLECTIONS:
        documents = state.get(name, [])
        if not isinstance(documents, list):
            raise ValueError(f"Invalid {name} collection in local database snapshot: {snapshot_path}")
        if documents:
            raw_client[DB_NAME][name].insert_many(documents)


if _use_mock_mongo:
    try:
        import mongomock
    except ImportError:
        client = _AsyncMongoClient(AsyncIOMotorClient(MONGO_URL))
        db = client[DB_NAME]
    else:
        raw_client = mongomock.MongoClient()
        _restore_local_snapshot(raw_client)
        client = _AsyncMongoClient(raw_client, lambda: _save_local_snapshot(raw_client))
        db = client[DB_NAME]
        logger.warning("Using local MongoDB fallback with on-disk set and job metadata persistence")
else:
    client = _AsyncMongoClient(AsyncIOMotorClient(MONGO_URL))
    db = client[DB_NAME]

if os.environ.get("USE_REMOTE_STORAGE", "0") == "1" and STORAGE_BASE:
    STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
else:
    STORAGE_URL = ""

_storage_key = None


async def _seed_local_data_async():
    existing = await db.users.find_one({"user_id": "test-user-qa"})
    if existing:
        return
    now = datetime.now(timezone.utc)
    await db.users.insert_one({
        "user_id": "test-user-qa",
        "email": "qa.tester@example.com",
        "name": "QA Tester",
        "picture": None,
        "created_at": now,
    })
    await db.user_sessions.insert_one({
        "user_id": "test-user-qa",
        "session_token": "test_session_qa_papercut",
        "expires_at": now.replace(year=now.year + 10),
        "created_at": now,
    })


def _seed_local_data():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_seed_local_data_async())
        return

    loop = asyncio.get_running_loop()
    loop.create_task(_seed_local_data_async())


_seed_local_data()


class _StorageResponse:
    def __init__(self, status_code: int, content: bytes = b"", payload: Optional[dict] = None):
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"Storage request failed with status {self.status_code}")

    def json(self):
        return dict(self._payload)


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    _storage_key = "local-storage-fallback"
    return _storage_key


def _local_storage_path(path: str) -> Path:
    safe = path.strip("/")
    if not safe:
        raise ValueError("Storage path cannot be empty")
    return LOCAL_STORAGE_ROOT / safe


def _storage_call(method: str, path: str, headers: Optional[dict] = None, **kw):
    if not STORAGE_URL:
        if method == "PUT":
            data = kw.get("data") or b""
            target = _local_storage_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return _StorageResponse(200, b"", {"path": path})
        if method == "GET":
            target = _local_storage_path(path)
            if target.exists():
                return _StorageResponse(200, target.read_bytes())
            return _StorageResponse(404, b"")
        return _StorageResponse(200, b"", {})

    force = False
    try:
        import requests
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
            return resp
        raise RuntimeError("Storage unreachable")
    except Exception:
        logger.warning("Remote storage unavailable; falling back to local filesystem storage")
        return _storage_call("PUT" if method == "PUT" else "GET", path, headers=headers, **kw)


async def put_object(path: str, data: bytes, content_type: str) -> str:
    resp = await asyncio.to_thread(_storage_call, "PUT", path, data=data, headers={"Content-Type": content_type})
    return resp.json()["path"]


async def get_object(path: str) -> bytes:
    resp = await asyncio.to_thread(_storage_call, "GET", path)
    return resp.content
