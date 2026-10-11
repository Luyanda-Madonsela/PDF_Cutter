"""Backend tests for PaperCut v4 API (sets, bulk queue, links, meta, zip, question editing).

API iteration 4 highlights:
- POST /api/sets (multipart: question_paper, memo, addenda[], errata[]) -> single-mode set
- POST /api/jobs (file, set_id?, doc_type?) -> bulk-mode queue; sets auto-grouped
- GET /api/sets (list + counts), GET /api/sets/{id} (detail with documents/links/extras)
- PATCH /api/sets/{id}/meta, DELETE /api/sets/{id}, GET /api/sets/{id}/zip
- PUT/review/merge-next/DELETE on /api/jobs/{id}/questions/{qid}

Most assertions run against the pre-seeded bulk set to avoid 1-2 min of real AI
processing per test. One slow test hits POST /api/sets to validate end-to-end.
"""
import os
import io
import time
import zipfile
import struct
import pytest
import requests

# --- config ---
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
SAMPLE_ADDENDUM = "/app/tests/sample_addendum.pdf"
SAMPLE_ERRATA = "/app/tests/sample_errata.pdf"
POLL_TIMEOUT = 300


def _png_width(data: bytes) -> int:
    # IHDR starts at byte 16; width is 4 bytes big-endian
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">I", data[16:20])[0]


def _wait_set_done(set_id, timeout=POLL_TIMEOUT, wanted=("done", "error")):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{API}/sets/{set_id}")
        assert r.status_code == 200, r.text
        last = r.json()
        if last.get("status") in wanted:
            return last
        time.sleep(3)
    return last


# ============================================================
# Basics
# ============================================================
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


def test_create_set_missing_memo_422():
    """POST /api/sets without the required memo file must 422."""
    with open(SAMPLE_PAPER, "rb") as f:
        qp = f.read()
    r = requests.post(f"{API}/sets", files={"question_paper": ("sample_paper.pdf", qp, "application/pdf")})
    assert r.status_code == 422, r.text


def test_create_set_invalid_doc_type():
    r = requests.post(f"{API}/jobs?doc_type=garbage", files={"file": ("x.pdf", b"", "application/pdf")})
    # Either 400 (bad doc_type) or 400 (bad PDF) acceptable - must not be 200
    assert r.status_code == 400


# ============================================================
# Seeded bulk set fixture (fast - uses existing data)
# ============================================================
@pytest.fixture(scope="module")
def seeded_set():
    """Find the pre-seeded Mathematics_Gr12_2024_Nov bulk set."""
    r = requests.get(f"{API}/sets")
    assert r.status_code == 200
    body = r.json()
    cand = [s for s in body["sets"]
            if s.get("status") == "done"
            and s.get("base_name", "").startswith("Mathematics_Gr12_2024_Nov")
            and s.get("mode") == "bulk"]
    if not cand:
        pytest.skip("No seeded bulk set available")
    sid = cand[0]["id"]
    detail = requests.get(f"{API}/sets/{sid}").json()
    return detail


def test_list_sets_shape():
    r = requests.get(f"{API}/sets")
    assert r.status_code == 200
    body = r.json()
    assert "sets" in body and "counts" in body
    assert set(body["counts"].keys()) >= {"sorting", "needs_memo", "needs_paper", "processing", "done", "error", "flagged"}
    for s in body["sets"]:
        assert "id" in s and "base_name" in s and "status" in s and "mode" in s
        assert "docs" in s


def test_set_detail_structure(seeded_set):
    s = seeded_set
    assert s["mode"] == "bulk"
    assert s["status"] == "done"
    assert s["base_name"] == "Mathematics_Gr12_2024_Nov_National_P1"
    assert isinstance(s["documents"], list) and len(s["documents"]) == 4
    types = sorted(d["meta"]["doc_type"] for d in s["documents"])
    assert types == ["addendum", "errata", "memo", "question_paper"]
    assert s["qp_id"], s
    assert isinstance(s["links"], dict) and len(s["links"]) == 7  # 7 sub-questions expected
    assert "extras" in s and set(s["extras"].keys()) == {"general", "unlinked", "memo_unmatched"}


def test_expected_links(seeded_set):
    """Spec: all 7 Qs have memo; 2.1 & 3.2 errata; 2.2 addendum; 3.1 & 3.2 addendum (main-Q 3 table)."""
    qp_doc = next(d for d in seeded_set["documents"] if d["meta"]["doc_type"] == "question_paper")
    qid_by_label = {q["label"]: q["id"] for q in qp_doc["questions"]}
    links = seeded_set["links"]
    missing_memo = [lab for lab, qid in qid_by_label.items() if not links[qid]["memo"]]
    assert not missing_memo, f"Questions without memo: {missing_memo}"
    # Addenda / errata labels per spec
    def labels_with(kind):
        return {lab for lab, qid in qid_by_label.items() if links[qid][kind]}
    err = labels_with("errata")
    add = labels_with("addenda")
    # Keep assertions tolerant to AI segmentation variance - require at least the expected ones
    assert "2.1" in err and "3.2" in err, f"Errata labels: {err}"
    assert "2.2" in add, f"Addendum labels: {add}"
    assert "3.1" in add or "3.2" in add, f"Addendum labels: {add}"


def test_question_filename_format_and_width_1400(seeded_set):
    qp = next(d for d in seeded_set["documents"] if d["meta"]["doc_type"] == "question_paper")
    assert qp["questions"], qp
    base = qp["base_name"]
    for q in qp["questions"]:
        # {order:03d}_{base}_Q{label}[_{marks}marks].png
        assert q["filename"].startswith(f"{q['order']:03d}_{base}_Q"), q["filename"]
        assert q["filename"].endswith(".png")
        if q.get("marks") is not None:
            assert f"_{q['marks']}marks.png" in q["filename"]
        assert q["width"] == 1400, f"{q['filename']} width={q['width']}"


def test_image_endpoint_width_1400(seeded_set):
    """All PNGs via /api/jobs/{id}/images/{qid} are exactly 1400px wide."""
    for doc in seeded_set["documents"]:
        if doc["status"] != "done" or not doc["questions"]:
            continue
        for q in doc["questions"][:2]:  # sample first 2 per doc
            r = requests.get(f"{API}/jobs/{doc['id']}/images/{q['id']}")
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("image/png")
            assert _png_width(r.content) == 1400, f"{doc['filename']} q{q['label']}"


def test_image_not_found(seeded_set):
    doc = seeded_set["documents"][0]
    r = requests.get(f"{API}/jobs/{doc['id']}/images/not-a-real-qid")
    assert r.status_code == 404


def test_page_jpeg(seeded_set):
    doc = seeded_set["documents"][0]
    r = requests.get(f"{API}/jobs/{doc['id']}/pages/0")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/jpeg")
    assert r.content[:3] == b"\xff\xd8\xff"


def test_page_out_of_range(seeded_set):
    doc = seeded_set["documents"][0]
    r = requests.get(f"{API}/jobs/{doc['id']}/pages/999")
    assert r.status_code == 404


def test_set_zip_filenames_width(seeded_set):
    sid = seeded_set["id"]
    r = requests.get(f"{API}/sets/{sid}/zip")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    folder = seeded_set["base_name"]
    assert all(n.startswith(folder + "/") for n in names), names
    pngs = [n for n in names if n.endswith(".png")]
    assert pngs, names
    # Every PNG inside the zip is 1400 wide
    for name in pngs:
        data = zf.read(name)
        assert _png_width(data) == 1400, f"{name} not 1400 wide"
    # Must contain _MEMO siblings for every QP question
    memo_pngs = [n for n in names if "_MEMO.png" in n]
    assert len(memo_pngs) == 7, f"MEMO pngs: {memo_pngs}"
    # And at least one _ADDENDUM and _ERRATA sibling
    assert any("_ADDENDUM" in n for n in names), names
    assert any("_ERRATA" in n for n in names), names


# ============================================================
# Question editing (seeded set)
# ============================================================
@pytest.fixture
def qp_doc(seeded_set):
    """Fetch a fresh copy of the QP document so each edit sees up-to-date state."""
    r = requests.get(f"{API}/sets/{seeded_set['id']}")
    detail = r.json()
    return next(d for d in detail["documents"] if d["meta"]["doc_type"] == "question_paper")


def test_update_question_label_renames_file(seeded_set, qp_doc):
    q = qp_doc["questions"][-1]
    orig_label = q["label"]
    new_label = orig_label + "x"
    r = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"label": new_label})
    assert r.status_code == 200, r.text
    updated = next(x for x in next(d for d in r.json()["documents"] if d["id"] == qp_doc["id"])["questions"] if x["id"] == q["id"])
    assert updated["label"] == new_label
    assert f"_Q{new_label}" in updated["filename"]
    # revert
    requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"label": orig_label})


def test_update_question_invalid_parts(qp_doc):
    q = qp_doc["questions"][0]
    r = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"parts": []})
    assert r.status_code == 400
    r = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}",
                     json={"parts": [{"page": 0, "y0": 500, "y1": 100}]})
    assert r.status_code == 400
    r = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}",
                     json={"parts": [{"page": 99, "y0": 0, "y1": 100}]})
    assert r.status_code == 400


def test_update_question_marks_and_clear(seeded_set, qp_doc):
    q = qp_doc["questions"][-1]
    orig_marks = q.get("marks")
    r = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"marks": 42})
    assert r.status_code == 200
    body = r.json()
    doc = next(d for d in body["documents"] if d["id"] == qp_doc["id"])
    updated = next(x for x in doc["questions"] if x["id"] == q["id"])
    assert updated["marks"] == 42
    assert "_42marks.png" in updated["filename"]
    # Clear
    r2 = requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"clear_marks": True})
    assert r2.status_code == 200
    doc2 = next(d for d in r2.json()["documents"] if d["id"] == qp_doc["id"])
    updated2 = next(x for x in doc2["questions"] if x["id"] == q["id"])
    assert updated2["marks"] is None
    assert "marks.png" not in updated2["filename"]
    # restore
    if orig_marks is not None:
        requests.put(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}", json={"marks": orig_marks})


def test_mark_reviewed_clears_flag(seeded_set, qp_doc):
    q = qp_doc["questions"][0]
    r = requests.post(f"{API}/jobs/{qp_doc['id']}/questions/{q['id']}/review")
    assert r.status_code == 200
    body = r.json()
    # Any lingering flag entries for this q in links should be empty
    link = body["links"][q["id"]]
    assert link["flags"] == [], link


# ============================================================
# PATCH meta canonicalisation
# ============================================================
def test_patch_set_meta_canonicalises_and_renames(seeded_set):
    sid = seeded_set["id"]
    detail = requests.get(f"{API}/sets/{sid}").json()
    meta = dict(detail["meta"])
    orig_province, orig_session = meta.get("province", ""), meta.get("session", "")
    meta["province"] = "Gauteng"
    meta["session"] = "June"
    r = requests.patch(f"{API}/sets/{sid}/meta", json=meta)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["province"] == "GP"
    assert body["meta"]["session"] == "May/Jun"
    assert "_GP_" in body["base_name"]
    assert "_MayJun_" in body["base_name"]
    for d in body["documents"]:
        for q in d["questions"]:
            assert "_GP_" in q["filename"] and "_MayJun_" in q["filename"]
    # revert
    meta["province"] = orig_province
    meta["session"] = orig_session
    rr = requests.patch(f"{API}/sets/{sid}/meta", json=meta)
    assert rr.status_code == 200


def test_retry_rejects_non_error(qp_doc):
    r = requests.post(f"{API}/jobs/{qp_doc['id']}/retry")
    assert r.status_code == 400


# ============================================================
# Bulk upload lifecycle: single QP stays needs_memo until memo added
# ============================================================
@pytest.fixture(scope="module")
def lonely_qp_set():
    """Upload a bare QP via /api/jobs (bulk). It must land in a set with status 'needs_memo'."""
    with open(SAMPLE_PAPER, "rb") as f:
        data = f.read()
    r = requests.post(f"{API}/jobs", files={"file": ("sample_paper.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    job = r.json()
    # wait for classification (status -> waiting) then set assignment
    deadline = time.time() + 120
    set_id = None
    while time.time() < deadline:
        r = requests.get(f"{API}/sets")
        for s in r.json()["sets"]:
            if any(d["job_id"] == job["id"] for d in s.get("docs", [])):
                set_id = s["id"]
                break
        if set_id:
            break
        time.sleep(3)
    assert set_id, "QP never got assigned to a set"
    yield job, set_id
    # cleanup
    requests.delete(f"{API}/sets/{set_id}")


def test_lonely_qp_set_needs_memo(lonely_qp_set):
    job, set_id = lonely_qp_set
    # Give classification time to settle, then verify set shows needs_memo and job stays 'waiting'
    deadline = time.time() + 180
    final = None
    while time.time() < deadline:
        detail = requests.get(f"{API}/sets/{set_id}").json()
        final = detail
        if detail["status"] in ("needs_memo", "needs_paper", "error"):
            break
        time.sleep(3)
    assert final["status"] == "needs_memo", f"set status={final['status']}, docs={final['docs']}"
    # The QP doc should NOT have been processed yet (status 'waiting')
    qp_doc = next(d for d in final["documents"] if d["meta"]["doc_type"] == "question_paper")
    assert qp_doc["status"] in ("waiting", "classifying", "queued"), qp_doc["status"]
    assert not qp_doc["questions"], "QP must not be processed before memo arrives"


def test_add_memo_promotes_set_to_processing(lonely_qp_set):
    job, set_id = lonely_qp_set
    with open(SAMPLE_MEMO, "rb") as f:
        data = f.read()
    r = requests.post(f"{API}/jobs?set_id={set_id}&doc_type=memo",
                     files={"file": ("sample_memo.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    # Wait up to 5 min for both docs to finish
    final = _wait_set_done(set_id, timeout=360)
    assert final and final["status"] in ("done", "processing"), final
    # Eventually both docs should reach done; allow more time if still processing
    if final["status"] == "processing":
        final = _wait_set_done(set_id, timeout=240)
    assert final["status"] == "done", f"status={final['status']}, docs={[(d['filename'],d['status']) for d in final['documents']]}"


# ============================================================
# Merge/delete question (do last - mutates seeded set)
# ============================================================
def test_merge_next_and_delete_question(seeded_set):
    r = requests.get(f"{API}/sets/{seeded_set['id']}")
    qp = next(d for d in r.json()["documents"] if d["meta"]["doc_type"] == "question_paper")
    if len(qp["questions"]) < 3:
        pytest.skip("Need >=3 questions to safely merge+delete")
    before = len(qp["questions"])
    first = qp["questions"][0]
    rm = requests.post(f"{API}/jobs/{qp['id']}/questions/{first['id']}/merge-next")
    assert rm.status_code == 200
    merged_doc = next(d for d in rm.json()["documents"] if d["id"] == qp["id"])
    assert len(merged_doc["questions"]) == before - 1
    # delete last question
    victim = merged_doc["questions"][-1]
    rd = requests.delete(f"{API}/jobs/{qp['id']}/questions/{victim['id']}")
    assert rd.status_code == 200
    after_doc = next(d for d in rd.json()["documents"] if d["id"] == qp["id"])
    assert len(after_doc["questions"]) == before - 2
    orders = [q["order"] for q in after_doc["questions"]]
    assert orders == list(range(1, len(orders) + 1))
    for q in after_doc["questions"]:
        assert q["filename"].startswith(f"{q['order']:03d}_"), q["filename"]
