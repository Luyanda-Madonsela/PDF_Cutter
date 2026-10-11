"""Iteration 13: Google Drive API not-enabled error handling.

Verifies that when the user's Google Cloud project has the Drive API disabled
(HttpError 403 accessNotConfigured), each entry-point returns a readable error
rather than a raw HttpError dump, and does so quickly (no long retry loop).

If the user has enabled the API during testing, calls will succeed instead and
tests will skip (reported as PASS per spec).
"""
import os
import time
import asyncio
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
AUTH = {"Authorization": "Bearer test_session_qa_papercut"}
IEB_SET_ID = "4c41f0c1-f54f-49ec-b5c6-db27470415b7"  # IEB Physical Sciences, done, drive=null
ERR_PHRASE = "Google Drive API is not enabled"


# Shared event loop + motor client bound to it (motor is loop-bound)
_LOOP = asyncio.new_event_loop()


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL, io_loop=_LOOP)
    return client[DB_NAME]


def arun(coro):
    return _LOOP.run_until_complete(coro)


# --- Test 1: /api/drive/search ---
def test_search_returns_readable_400_fast():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/drive/search", params={"q": "maths"}, headers=AUTH, timeout=30)
    elapsed = time.time() - t0
    print(f"[search] status={r.status_code} elapsed={elapsed:.2f}s")
    if r.status_code == 200:
        body = r.json()
        assert "files" in body
        print(f"[search] PASS (API enabled): {len(body['files'])} files, token={bool(body.get('next_page_token'))}")
        return
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    detail = r.json().get("detail", "")
    assert ERR_PHRASE in detail, f"detail missing phrase: {detail!r}"
    assert "HttpError" not in detail, f"raw HttpError leaked: {detail!r}"
    assert elapsed < 10, f"took too long ({elapsed:.1f}s)"


# --- Test 2: scan + import-status ---
def test_scan_import_status_readable():
    db = _db()
    r = requests.post(f"{BASE_URL}/api/drive/scan", json={"limit": 50}, headers=AUTH, timeout=15)
    assert r.status_code in (200, 409), f"scan start got {r.status_code}: {r.text[:200]}"
    if r.status_code == 409:
        pytest.skip("Another import already running")
    doc = None
    for _ in range(45):
        time.sleep(1)
        s = requests.get(f"{BASE_URL}/api/drive/import-status", headers=AUTH, timeout=10)
        assert s.status_code == 200
        doc = s.json()
        if doc.get("status") in ("error", "done"):
            break
    print(f"[scan] last: {doc}")
    assert doc is not None
    # If API is NOT enabled, expect error with readable msg
    if doc.get("status") == "error":
        err = doc.get("error", "")
        assert ERR_PHRASE in err, f"error missing phrase: {err!r}"
        assert "HttpError" not in err, f"raw HttpError leaked: {err!r}"
        return
    # API enabled path: verify no raw HttpError / accessNotConfigured leaked anywhere
    blob = str(doc)
    assert "accessNotConfigured" not in blob, f"leak: {blob}"
    assert "HttpError" not in blob, f"HttpError leak: {blob}"
    # Progress check: either done, or scanning/importing with progress
    assert doc.get("status") in ("done", "scanning", "importing"), f"unexpected: {doc}"
    print(f"[scan] PASS (API enabled): status={doc.get('status')}, done={doc.get('done')}, imported={doc.get('imported')}")


# --- Test 3: /api/drive/sets/{id}/send ---
def test_send_set_readable_error():
    db = _db()
    r = requests.post(f"{BASE_URL}/api/drive/sets/{IEB_SET_ID}/send", headers=AUTH, timeout=15)
    assert r.status_code == 200, f"send got {r.status_code}: {r.text[:300]}"
    final = None
    try:
        for _ in range(90):  # upload can take time
            time.sleep(1)
            doc = arun(db.sets.find_one({"_id": IEB_SET_ID}, {"drive": 1}))
            d = (doc or {}).get("drive") or {}
            if d.get("status") in ("error", "done"):
                final = d
                break
        print(f"[send] final set.drive: {final}")
        assert final is not None, "set.drive never terminal"
        if final["status"] == "error":
            err = final.get("error", "") or ""
            assert ERR_PHRASE in err, f"readable phrase missing: {err!r}"
            assert "HttpError" not in err, f"raw HttpError leaked: {err!r}"
        else:
            print(f"[send] PASS (API enabled): uploaded={final.get('uploaded')}")
    finally:
        # Reset per spec
        arun(db.sets.update_one({"_id": IEB_SET_ID}, {"$set": {"drive": None}}))


# --- Test 4: PUT /api/drive/settings ---
def test_put_settings_readable_error():
    db = _db()
    before = arun(db.settings.find_one({"_id": "drive"})) or {}
    payload = {
        "root_link": "https://drive.google.com/drive/folders/1Rbo3-EfjwO3mufbN12jU514FPfd9ur2i",
        "root_path": "CAPS & IEB Past Papers",
    }
    t0 = time.time()
    r = requests.put(f"{BASE_URL}/api/drive/settings", json=payload, headers=AUTH, timeout=30)
    elapsed = time.time() - t0
    print(f"[settings] status={r.status_code} elapsed={elapsed:.2f}s body={r.text[:300]}")
    try:
        if r.status_code == 200:
            print(f"[settings] PASS (API enabled): {r.json()}")
            return
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert ERR_PHRASE in detail, f"detail missing phrase: {detail!r}"
        assert "HttpError" not in detail, f"raw HttpError leaked: {detail!r}"
        assert elapsed < 15, f"took too long ({elapsed:.1f}s)"
    finally:
        if before:
            fields = {k: v for k, v in before.items() if k != "_id"}
            arun(db.settings.update_one({"_id": "drive"}, {"$set": fields}, upsert=True))
