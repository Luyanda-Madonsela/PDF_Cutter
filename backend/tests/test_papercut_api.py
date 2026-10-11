"""Backend tests for PaperCut API"""
import os
import time
import io
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://papercut-sa.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
SAMPLE_PDF = "/app/tests/sample_paper.pdf"


@pytest.fixture(scope="session")
def session():
    return requests.Session()


# ---------- health ----------
def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    assert "PaperCut" in r.json().get("message", "")


# ---------- upload validation ----------
def test_upload_non_pdf_rejected(session):
    r = session.post(f"{API}/jobs", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_upload_corrupted_pdf_rejected(session):
    r = session.post(f"{API}/jobs", files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 400


# ---------- full lifecycle ----------
@pytest.fixture(scope="module")
def finished_job():
    with open(SAMPLE_PDF, "rb") as f:
        r = requests.post(f"{API}/jobs", files={"file": ("sample_paper.pdf", f.read(), "application/pdf")})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["status"] in ("queued", "processing")
    assert "id" in job
    job_id = job["id"]

    # poll up to 90s
    deadline = time.time() + 120
    final = None
    while time.time() < deadline:
        g = requests.get(f"{API}/jobs/{job_id}")
        assert g.status_code == 200
        final = g.json()
        if final["status"] in ("done", "error"):
            break
        time.sleep(2)
    assert final is not None
    assert final["status"] == "done", f"Job did not finish successfully: {final}"
    return final


def test_job_processing_result(finished_job):
    j = finished_job
    assert j["total_pages"] == 3
    assert j["pages_done"] == 3
    assert isinstance(j["questions"], list)
    assert len(j["questions"]) >= 5, f"Expected >=5 questions, got {len(j['questions'])}: {[q['label'] for q in j['questions']]}"
    labels = [q["label"] for q in j["questions"]]
    print(f"Detected labels: {labels}")
    # order ascending
    orders = [q["order"] for q in j["questions"]]
    assert orders == sorted(orders)
    # filename format
    for q in j["questions"]:
        assert q["filename"].endswith(".png")
        assert f"{q['order']:03d}_Q" in q["filename"]


def test_image_endpoint(finished_job):
    j = finished_job
    q = j["questions"][0]
    r = requests.get(f"{API}/jobs/{j['id']}/images/{q['filename']}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_endpoint_404(finished_job):
    r = requests.get(f"{API}/jobs/{finished_job['id']}/images/nope.png")
    assert r.status_code == 404


def test_zip_download(finished_job):
    j = finished_job
    r = requests.get(f"{API}/jobs/{j['id']}/zip")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert all(n.startswith("sample_paper/") for n in names)
    assert len(names) == len(j["questions"])
    for q in j["questions"]:
        assert f"sample_paper/{q['filename']}" in names


def test_list_jobs(finished_job):
    r = requests.get(f"{API}/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert any(x["id"] == finished_job["id"] for x in jobs)


def test_delete_job_soft(finished_job):
    jid = finished_job["id"]
    r = requests.delete(f"{API}/jobs/{jid}")
    assert r.status_code == 200
    g = requests.get(f"{API}/jobs/{jid}")
    assert g.status_code == 404
    lst = requests.get(f"{API}/jobs").json()
    assert all(x["id"] != jid for x in lst)
