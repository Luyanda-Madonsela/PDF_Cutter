"""Iteration 8: Drive settings endpoint, recrop-preview, per-set recrop (on cloned set),
plan_uploads root parameter.

Avoids direct motor DB usage so pytest-xdist multi-worker runs are stable."""
import os
import sys
import time
import uuid
import json
import subprocess
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://papercut-sa.preview.emergentagent.com"
API = f"{BASE_URL}/api"
H = {"Authorization": "Bearer test_session_qa_papercut"}

ORIGINAL_ROOT = "Fundani Group (Holdings Company)/ResourceWiz Inc/Past Paper Database/CAPS & IEB Past Papers"


def _get(p, **kw): return requests.get(f"{API}{p}", headers=H, **kw)
def _post(p, **kw): return requests.post(f"{API}{p}", headers=H, **kw)
def _put(p, **kw): return requests.put(f"{API}{p}", headers=H, **kw)
def _delete(p, **kw): return requests.delete(f"{API}{p}", headers=H, **kw)


# ============================================================
# Drive settings
# ============================================================
def test_drive_settings_empty_rejected():
    r = _put("/drive/settings", json={"root_path": ""})
    assert r.status_code == 400, r.text


def test_drive_settings_my_drive_prefix_stripped_and_persisted():
    new_root = "My Drive/TEST_PaperCut_Root/Subfolder"
    r = _put("/drive/settings", json={"root_path": new_root})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checked"] is False
    assert body["root"] == "My Drive/TEST_PaperCut_Root/Subfolder", body

    s = _get("/drive/status").json()
    assert s["root"] == "My Drive/TEST_PaperCut_Root/Subfolder", s

    # Restore
    r2 = _put("/drive/settings", json={"root_path": ORIGINAL_ROOT})
    assert r2.status_code == 200
    assert r2.json()["root"] == "My Drive/" + ORIGINAL_ROOT
    assert _get("/drive/status").json()["root"] == "My Drive/" + ORIGINAL_ROOT


# ============================================================
# plan_uploads: subprocess so motor runs in a fresh process (xdist-safe)
# ============================================================
def test_plan_uploads_uses_root_param():
    sets = _get("/sets").json()["sets"]
    s = next((x for x in sets if x["status"] == "done"), None)
    if not s:
        pytest.skip("no done set")
    code = r"""
import asyncio, json, sys
sys.path.insert(0, "/app/backend")
import drive
from jobs import load_set, set_jobs

async def main(sid):
    ps = await load_set(sid)
    jobs = await set_jobs(sid)
    items = drive.plan_uploads(ps, jobs, ["Custom", "Root", "Here"])
    print(json.dumps([{"path": it["path"]} for it in items]))

asyncio.run(main(sys.argv[1]))
"""
    out = subprocess.check_output(["python3", "-c", code, s["id"]], cwd="/app/backend",
                                  env={**os.environ, "PYTHONPATH": "/app/backend"})
    items = json.loads(out.decode())
    assert items
    for it in items:
        assert it["path"][:3] == ["Custom", "Root", "Here"], it["path"]


# ============================================================
# Recrop preview
# ============================================================
def test_recrop_preview_shape():
    r = _get("/sets/recrop-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sets" in body and "edited" in body
    assert isinstance(body["sets"], int) and isinstance(body["edited"], int)
    assert body["edited"] <= body["sets"]
    assert body["sets"] >= 2


# ============================================================
# Per-set recrop
# ============================================================
def test_recrop_non_done_rejected():
    """Any id not in the done_qp_jobs list -> 400."""
    r = _post(f"/sets/{uuid.uuid4()}/recrop")
    assert r.status_code == 400, r.text


@pytest.fixture(scope="module")
def cloned_set_id():
    """Spawn clone_set.py in a subprocess so motor runs cleanly."""
    out = subprocess.check_output(["python3", "tests/clone_set.py"], cwd="/app/backend",
                                  env={**os.environ, "PYTHONPATH": "/app/backend"})
    nid = out.decode().strip().splitlines()[-1]
    if not nid or len(nid) < 10:
        pytest.skip("clone failed")
    yield nid
    _delete(f"/sets/{nid}")


def test_recrop_cloned_set_resets_qp_and_drive(cloned_set_id):
    sid = cloned_set_id
    before = _get(f"/sets/{sid}").json()
    other_docs = {d["id"]: d for d in before["documents"] if d["meta"]["doc_type"] != "question_paper"}
    qp_before = next(d for d in before["documents"] if d["meta"]["doc_type"] == "question_paper")
    assert qp_before["status"] == "done"
    assert qp_before["questions"]

    r = _post(f"/sets/{sid}/recrop")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body.get("drive") in (None, {}), body.get("drive")
    assert body["status"] == "processing", body["status"]

    qp_after = next(d for d in body["documents"] if d["meta"]["doc_type"] == "question_paper")
    assert qp_after["questions"] == [], qp_after
    assert qp_after["status"] != "done", qp_after["status"]

    for d in body["documents"]:
        if d["meta"]["doc_type"] == "question_paper":
            continue
        prev = other_docs[d["id"]]
        assert d["status"] == prev["status"], d
        assert len(d["questions"]) == len(prev["questions"])


def test_recrop_already_processing_rejected(cloned_set_id):
    """After previous test the set is processing; second recrop must 400."""
    r = _post(f"/sets/{cloned_set_id}/recrop")
    assert r.status_code == 400, r.text


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="Set RUN_SLOW=1 to execute (Gemini 1-4 min)")
def test_recrop_cloned_set_eventually_finishes(cloned_set_id):
    """Wait up to 5 min for Gemini to finish re-cropping."""
    sid = cloned_set_id
    deadline = time.time() + 300
    final = None
    while time.time() < deadline:
        d = _get(f"/sets/{sid}").json()
        if d["status"] == "done":
            final = d
            break
        if d["status"] == "error":
            pytest.fail(f"error: {d}")
        time.sleep(10)
    assert final, "Recrop did not finish in 5 min"
    qp = next(x for x in final["documents"] if x["meta"]["doc_type"] == "question_paper")
    assert qp["status"] == "done"
    assert qp["questions"]
