"""Iteration 9:
- Drive settings with root_link (Drive folder URL -> root_id) + root_path
- /api/drive status returns root_link
- drive.root_path() returns ['id:...', <path parts>]
- drive.plan_base uses 'id:<paper_folder_id>' when job has drive_source; PDFs with drive_source are not in plan
- drive import endpoints (search / import / scan / import-status) with Drive NOT connected -> 400
- Auth required (401)
- Undo crop endpoint on a cloned set.

Avoids direct motor use inside pytest-xdist workers via a subprocess helper where DB access needed.
"""
import os
import sys
import json
import subprocess
import uuid
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://papercut-sa.preview.emergentagent.com"
API = f"{BASE_URL}/api"
H = {"Authorization": "Bearer test_session_qa_papercut"}

ORIGINAL_LINK = "https://drive.google.com/drive/folders/1Rbo3-EfjwO3mufbN12jU514FPfd9ur2i"
ORIGINAL_PATH = "CAPS & IEB Past Papers"
ORIGINAL_ROOT_ID = "1Rbo3-EfjwO3mufbN12jU514FPfd9ur2i"


def _g(p, **kw): return requests.get(f"{API}{p}", headers=H, **kw)
def _p(p, **kw): return requests.post(f"{API}{p}", headers=H, **kw)
def _put(p, **kw): return requests.put(f"{API}{p}", headers=H, **kw)


# ---------------- Drive settings ----------------
class TestDriveSettings:
    def test_both_empty_rejected(self):
        r = _put("/drive/settings", json={"root_link": "", "root_path": ""})
        assert r.status_code == 400, r.text

    def test_non_drive_link_rejected(self):
        r = _put("/drive/settings", json={"root_link": "https://example.com/foo", "root_path": "x"})
        assert r.status_code == 400, r.text

    def test_folder_link_parsed(self):
        r = _put("/drive/settings", json={
            "root_link": "https://drive.google.com/drive/u/1/folders/1AbCDefGhIjKlMnOpQrStUvWxYz_test",
            "root_path": "TEST_CAPS Past Papers"
        })
        assert r.status_code == 200, r.text
        st = _g("/drive/status").json()
        assert st["root_id"] == "1AbCDefGhIjKlMnOpQrStUvWxYz_test"
        assert st["root_path"] == "TEST_CAPS Past Papers"
        assert st["root_link"] == "https://drive.google.com/drive/folders/1AbCDefGhIjKlMnOpQrStUvWxYz_test"

    def test_raw_id_accepted(self):
        r = _put("/drive/settings", json={"root_link": "1ZzYyXxWwVvUuTtSsRrQqPpOoNn_rawid", "root_path": "X"})
        assert r.status_code == 200, r.text
        st = _g("/drive/status").json()
        assert st["root_id"] == "1ZzYyXxWwVvUuTtSsRrQqPpOoNn_rawid"

    def test_restore_original(self):
        # Done last by name order? Use fixture-like direct call to avoid relying on order:
        r = _put("/drive/settings", json={"root_link": ORIGINAL_LINK, "root_path": ORIGINAL_PATH})
        assert r.status_code == 200, r.text
        st = _g("/drive/status").json()
        assert st["root_id"] == ORIGINAL_ROOT_ID
        assert st["root_path"] == ORIGINAL_PATH
        assert st["root_link"] == ORIGINAL_LINK


# ---------------- Auth ----------------
# Use a fresh Session to bypass module-level requests monkey-patching in test_papercut_api.py
_NOAUTH = requests.Session()


class TestAuth:
    def test_search_requires_auth(self):
        assert _NOAUTH.get(f"{API}/drive/search").status_code == 401

    def test_import_requires_auth(self):
        assert _NOAUTH.post(f"{API}/drive/import", json={"file_ids": []}).status_code == 401

    def test_scan_requires_auth(self):
        assert _NOAUTH.post(f"{API}/drive/scan", json={"limit": 50}).status_code == 401

    def test_import_status_requires_auth(self):
        assert _NOAUTH.get(f"{API}/drive/import-status").status_code == 401


# ---------------- Drive import endpoints (Drive NOT connected) ----------------
class TestDriveImport:
    def test_search_400_when_not_connected(self):
        r = _g("/drive/search", params={"q": "test"})
        assert r.status_code == 400 and "Connect Google Drive first" in r.text

    def test_import_400_when_not_connected(self):
        r = _p("/drive/import", json={"file_ids": ["fakeid"]})
        assert r.status_code == 400 and "Connect Google Drive first" in r.text

    def test_import_empty_list_400_when_not_connected(self):
        # service_or_400 runs before the empty check, so still "Connect Google Drive first"
        r = _p("/drive/import", json={"file_ids": []})
        assert r.status_code == 400 and "Connect Google Drive first" in r.text

    def test_scan_400_when_not_connected(self):
        r = _p("/drive/scan", json={"limit": 50})
        assert r.status_code == 400 and "Connect Google Drive first" in r.text

    def test_import_status_idle_or_last(self):
        r = _g("/drive/import-status")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("idle", "done", "error", "interrupted", "queued", "importing", "scanning")


# ---------------- Drive helpers unit (subprocess) ----------------
HELPER = r"""
import asyncio, sys, json
sys.path.insert(0, "/app/backend")
import drive
from models import PaperSet, Job, JobMeta, Question, Part as CropPart

async def main():
    # root_path() with current (restored) settings
    rp = await drive.root_path()
    # plan_base behaviour: craft job with drive_source
    import datetime
    meta = JobMeta(doc_type="question_paper", subject="Mathematics", grade="12", year="2023",
                   session="Nov", province="National", paper="1")
    q = Question(id="q1", label="1", parts=[CropPart(page=0, y0=0, y1=100)], storage_path="x", filename="x.png", flags=[])
    j = Job(id="j1", set_id="s1", filename="a.pdf", pdf_path="p", total_pages=1, status="done",
            meta=meta, questions=[q])
    j.drive_source = {"paper_folder_id": "FAKE_PAPER_FOLDER_ID", "file_id": "f", "parent_id": "p"}
    s = PaperSet(id="s1", meta=meta, base_name="x", status="done")
    base = drive.plan_base(s, [j], rp)
    # plan_uploads should NOT include PDFs with drive_source
    uploads = drive.plan_uploads(s, [j], rp)
    pdfs = [u for u in uploads if u.get("mime") == "application/pdf"]
    print(json.dumps({"rp": rp, "base": base, "pdfs": pdfs}))

asyncio.run(main())
"""


def test_root_path_and_plan_base_drive_source():
    out = subprocess.run([sys.executable, "-c", HELPER], capture_output=True, text=True, cwd="/app/backend")
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout.strip().splitlines()[-1])
    rp = data["rp"]
    assert rp[0] == f"id:{ORIGINAL_ROOT_ID}"
    assert "CAPS & IEB Past Papers" in rp
    assert data["base"] == ["id:FAKE_PAPER_FOLDER_ID"]
    assert data["pdfs"] == [], f"PDFs with drive_source leaked into plan: {data['pdfs']}"


# ---------------- Undo-crop on cloned set ----------------
@pytest.fixture(scope="module")
def cloned_set():
    out = subprocess.run([sys.executable, "tests/clone_set.py"], capture_output=True, text=True, cwd="/app/backend", env={**os.environ, "PYTHONPATH": "/app/backend"})
    assert out.returncode == 0, out.stderr
    sid = out.stdout.strip().splitlines()[-1]
    yield sid
    # soft-delete
    cleanup = f"""
import asyncio, sys
sys.path.insert(0, "/app/backend")
from core import db
async def main():
    await db.sets.update_one({{"_id": "{sid}"}}, {{"$set": {{"is_deleted": True}}}})
    await db.jobs.update_many({{"set_id": "{sid}"}}, {{"$set": {{"is_deleted": True}}}})
asyncio.run(main())
"""
    subprocess.run([sys.executable, "-c", cleanup], cwd="/app/backend")


def _find_qp_and_question(set_id: str):
    r = _g(f"/sets/{set_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    qp = next(d for d in data["documents"] if d["meta"]["doc_type"] == "question_paper")
    assert qp["questions"], "QP has no questions"
    q = qp["questions"][0]
    return qp["id"], q


class TestUndoCrop:
    def test_undo_crop_flow(self, cloned_set):
        qp_id, q = _find_qp_and_question(cloned_set)
        qid = q["id"]
        orig_parts = q["parts"]
        orig_storage = q["storage_path"]

        # Second undo first: should fail with no history
        r0 = _p(f"/jobs/{qp_id}/questions/{qid}/undo-crop")
        assert r0.status_code == 400, r0.text

        # Edit crop - shrink y1 by 20
        new_parts = []
        for p in orig_parts:
            np = dict(p)
            np["y1"] = max(np["y0"] + 10, np["y1"] - 20)
            new_parts.append(np)
        r1 = _put(f"/jobs/{qp_id}/questions/{qid}", json={"parts": new_parts})
        assert r1.status_code == 200, r1.text

        # Verify crop_history length 1 and contains old parts
        r_get = _g(f"/sets/{cloned_set}")
        qp = next(d for d in r_get.json()["documents"] if d["id"] == qp_id)
        q2 = next(x for x in qp["questions"] if x["id"] == qid)
        assert len(q2.get("crop_history", [])) == 1
        hist0 = q2["crop_history"][0]
        # Compare y1 values
        assert [p["y1"] for p in hist0] == [p["y1"] for p in orig_parts]
        new_storage = q2["storage_path"]

        # Undo
        r2 = _p(f"/jobs/{qp_id}/questions/{qid}/undo-crop")
        assert r2.status_code == 200, r2.text

        r_get2 = _g(f"/sets/{cloned_set}")
        qp2 = next(d for d in r_get2.json()["documents"] if d["id"] == qp_id)
        q3 = next(x for x in qp2["questions"] if x["id"] == qid)
        assert q3.get("crop_history", []) == []
        assert [p["y1"] for p in q3["parts"]] == [p["y1"] for p in orig_parts]
        assert q3["storage_path"] != new_storage  # new render

        # Second undo -> 400
        r3 = _p(f"/jobs/{qp_id}/questions/{qid}/undo-crop")
        assert r3.status_code == 400 and "No earlier crop" in r3.text

    def test_erase_preserves_crop_history(self, cloned_set):
        qp_id, q = _find_qp_and_question(cloned_set)
        qid = q["id"]
        # Create a crop_history entry via edit
        new_parts = [{**p, "y1": max(p["y0"] + 10, p["y1"] - 15)} for p in q["parts"]]
        assert _put(f"/jobs/{qp_id}/questions/{qid}", json={"parts": new_parts}).status_code == 200

        # Apply erase with empty boxes (rejects)
        r = _p(f"/jobs/{qp_id}/questions/{qid}/erase", json={"boxes": [], "manual": []})
        assert r.status_code == 200, r.text

        r_get = _g(f"/sets/{cloned_set}")
        qp = next(d for d in r_get.json()["documents"] if d["id"] == qp_id)
        q2 = next(x for x in qp["questions"] if x["id"] == qid)
        assert len(q2.get("crop_history", [])) == 1, "Erase should preserve crop_history"
