"""Backend tests for PaperCut v2 API (bulk queue, meta, pairing, crop editing, zip)."""
import os
import time
import io
import zipfile
import pytest
import requests

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"
SAMPLE_PAPER = "/app/tests/sample_paper.pdf"
SAMPLE_MEMO = "/app/tests/sample_memo.pdf"
POLL_TIMEOUT = 240  # seconds per job (real AI call ~15-25s each, queued sequential)


def _poll_done(job_id, timeout=POLL_TIMEOUT):
    deadline = time.time() + timeout
    final = None
    while time.time() < deadline:
        g = requests.get(f"{API}/jobs/{job_id}")
        assert g.status_code == 200
        final = g.json()
        if final["status"] in ("done", "error"):
            return final
        time.sleep(2)
    return final


def _upload(path, pair_with=None):
    with open(path, "rb") as f:
        data = f.read()
    url = f"{API}/jobs"
    if pair_with:
        url += f"?pair_with={pair_with}"
    r = requests.post(url, files={"file": (os.path.basename(path), data, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- basics ----------
def test_root():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert "PaperCut" in r.json().get("message", "")


def test_upload_non_pdf_rejected():
    r = requests.post(f"{API}/jobs", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_upload_corrupted_pdf_rejected():
    r = requests.post(f"{API}/jobs", files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 400


def test_list_jobs_shape():
    r = requests.get(f"{API}/jobs")
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body and "counts" in body
    assert set(body["counts"].keys()) >= {"queued", "processing", "done", "error"}
    for j in body["jobs"]:
        # list summary should NOT include questions / page_paths
        assert "questions" not in j
        assert "page_paths" not in j


# ---------- bulk queue + pairing lifecycle ----------
@pytest.fixture(scope="module")
def paired_jobs():
    """Upload QP + memo in rapid succession, wait for both to finish, return (qp, memo) details."""
    qp = _upload(SAMPLE_PAPER)
    memo = _upload(SAMPLE_MEMO)
    assert qp["status"] in ("queued", "processing")
    assert memo["status"] in ("queued", "processing")

    qp_final = _poll_done(qp["id"])
    memo_final = _poll_done(memo["id"])
    assert qp_final and qp_final["status"] == "done", qp_final
    assert memo_final and memo_final["status"] == "done", memo_final
    # re-fetch to let pairing propagate
    time.sleep(2)
    qp_final = requests.get(f"{API}/jobs/{qp['id']}").json()
    memo_final = requests.get(f"{API}/jobs/{memo['id']}").json()
    return qp_final, memo_final


def test_meta_detected_and_base_name(paired_jobs):
    qp, memo = paired_jobs
    # Expect Mathematics / Grade 12 / 2024 / November / Paper 1 from the sample fixtures
    assert qp["meta"]["subject"].lower().startswith("math")
    assert qp["meta"]["grade"] == "12"
    assert qp["meta"]["year"] == "2024"
    assert qp["meta"]["doc_type"] == "question_paper"
    assert qp["base_name"] == "Mathematics_Gr12_2024_Nov_P1", qp["base_name"]
    assert memo["meta"]["doc_type"] == "memo"
    assert memo["base_name"].endswith("_MEMO")


def test_jobs_auto_paired(paired_jobs):
    qp, memo = paired_jobs
    assert qp["paired_job_id"] == memo["id"]
    assert memo["paired_job_id"] == qp["id"]
    # /jobs/{id} should expose `paired` dict and pair_map
    assert qp.get("paired"), qp.get("paired")
    assert qp["paired"]["job_id"] == memo["id"]
    assert isinstance(qp.get("pair_map"), dict)
    # At least some labels should match between QP and memo
    assert len(qp["pair_map"]) >= 1, qp["pair_map"]


def test_question_filename_format(paired_jobs):
    qp, _ = paired_jobs
    for q in qp["questions"]:
        assert q["filename"].startswith(qp["base_name"] + "_")
        assert q["filename"].endswith(".png")
        assert f"_{q['order']:03d}_Q" in q["filename"]


def test_image_endpoint_by_qid(paired_jobs):
    qp, _ = paired_jobs
    q = qp["questions"][0]
    r = requests.get(f"{API}/jobs/{qp['id']}/images/{q['id']}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_endpoint_404(paired_jobs):
    qp, _ = paired_jobs
    r = requests.get(f"{API}/jobs/{qp['id']}/images/does-not-exist")
    assert r.status_code == 404


def test_page_endpoint_jpeg(paired_jobs):
    qp, _ = paired_jobs
    r = requests.get(f"{API}/jobs/{qp['id']}/pages/0")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/jpeg")
    assert r.content[:3] == b"\xff\xd8\xff"


def test_page_endpoint_out_of_range(paired_jobs):
    qp, _ = paired_jobs
    r = requests.get(f"{API}/jobs/{qp['id']}/pages/999")
    assert r.status_code == 404


def test_zip_contains_memo_pairs(paired_jobs):
    qp, memo = paired_jobs
    r = requests.get(f"{API}/jobs/{qp['id']}/zip")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    folder = qp["base_name"]
    assert all(n.startswith(folder + "/") for n in names), names
    # At least one _MEMO.png present
    memo_pngs = [n for n in names if n.endswith("_MEMO.png")]
    assert len(memo_pngs) >= 1, names
    # Should equal count of pair_map
    assert len(memo_pngs) == len(qp["pair_map"]), f"memo_pngs={memo_pngs} pair_map={qp['pair_map']}"
    # Each question filename is included
    for q in qp["questions"]:
        assert f"{folder}/{q['filename']}" in names


# ---------- question editing ----------
def test_update_question_label(paired_jobs):
    qp, _ = paired_jobs
    q = qp["questions"][-1]  # pick last so order renumbering won't break fixture
    new_label = q["label"] + "x"
    r = requests.put(f"{API}/jobs/{qp['id']}/questions/{q['id']}", json={"label": new_label})
    assert r.status_code == 200
    body = r.json()
    updated = next(x for x in body["questions"] if x["id"] == q["id"])
    assert updated["label"] == new_label
    assert new_label.replace(".", ".") in updated["filename"] or updated["label"] in updated["filename"]
    # revert
    r2 = requests.put(f"{API}/jobs/{qp['id']}/questions/{q['id']}", json={"label": q["label"]})
    assert r2.status_code == 200


def test_update_question_invalid_parts(paired_jobs):
    qp, _ = paired_jobs
    q = qp["questions"][0]
    # bad: empty parts
    r = requests.put(f"{API}/jobs/{qp['id']}/questions/{q['id']}", json={"parts": []})
    assert r.status_code == 400
    # bad: y1 < y0
    r2 = requests.put(f"{API}/jobs/{qp['id']}/questions/{q['id']}",
                      json={"parts": [{"page": 0, "y0": 500, "y1": 100}]})
    assert r2.status_code == 400
    # bad: page out of range
    r3 = requests.put(f"{API}/jobs/{qp['id']}/questions/{q['id']}",
                      json={"parts": [{"page": 99, "y0": 0, "y1": 100}]})
    assert r3.status_code == 400


# ---------- meta patch (destructive to pair_map) : do last-ish ----------
def test_patch_meta_renames_filenames(paired_jobs):
    qp, _ = paired_jobs
    detail = requests.get(f"{API}/jobs/{qp['id']}").json()
    meta = dict(detail["meta"])
    meta["year"] = "2023"
    r = requests.patch(f"{API}/jobs/{qp['id']}/meta", json=meta)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["year"] == "2023"
    assert "2023" in body["base_name"]
    for q in body["questions"]:
        assert "2023" in q["filename"]
    # revert to re-pair
    meta["year"] = "2024"
    r2 = requests.patch(f"{API}/jobs/{qp['id']}/meta", json=meta)
    assert r2.status_code == 200


def test_retry_rejects_non_error_jobs(paired_jobs):
    qp, _ = paired_jobs
    r = requests.post(f"{API}/jobs/{qp['id']}/retry")
    assert r.status_code == 400


# ---------- forced memo pair_with and delete-unpair ----------
def test_pair_with_forces_memo_and_delete_unpairs():
    """Upload a new QP + attach memo via ?pair_with=; then delete memo, QP must unpair."""
    qp = _upload(SAMPLE_PAPER)
    qp_final = _poll_done(qp["id"])
    assert qp_final["status"] == "done"

    memo = _upload(SAMPLE_MEMO, pair_with=qp["id"])
    assert memo["forced_memo"] is True
    assert memo["paired_job_id"] == qp["id"]

    memo_final = _poll_done(memo["id"])
    assert memo_final["status"] == "done"
    assert memo_final["meta"]["doc_type"] == "memo"

    qp_now = requests.get(f"{API}/jobs/{qp['id']}").json()
    assert qp_now["paired_job_id"] == memo["id"]

    # delete memo -> QP must unpair
    rd = requests.delete(f"{API}/jobs/{memo['id']}")
    assert rd.status_code == 200
    qp_after = requests.get(f"{API}/jobs/{qp['id']}").json()
    assert qp_after["paired_job_id"] in (None,), qp_after["paired_job_id"]

    # cleanup
    requests.delete(f"{API}/jobs/{qp['id']}")


# ---------- merge / delete question (do last; mutates fixture) ----------
def test_merge_next_and_delete_question(paired_jobs):
    qp, _ = paired_jobs
    # re-fetch to get fresh question list after prior edits
    detail = requests.get(f"{API}/jobs/{qp['id']}").json()
    questions = detail["questions"]
    if len(questions) < 2:
        pytest.skip("Not enough questions to merge")
    before = len(questions)
    first = questions[0]
    r = requests.post(f"{API}/jobs/{qp['id']}/questions/{first['id']}/merge-next")
    assert r.status_code == 200
    merged = r.json()
    assert len(merged["questions"]) == before - 1

    # delete the (now) last question
    victim = merged["questions"][-1]
    rd = requests.delete(f"{API}/jobs/{qp['id']}/questions/{victim['id']}")
    assert rd.status_code == 200
    after = rd.json()
    assert len(after["questions"]) == before - 2
    # orders should be sequential 1..N
    orders = [q["order"] for q in after["questions"]]
    assert orders == list(range(1, len(orders) + 1))
    # filenames reflect order
    for q in after["questions"]:
        assert f"_{q['order']:03d}_Q" in q["filename"]
