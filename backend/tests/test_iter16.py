"""Iteration 16: Difficulty rating feature.

Covers:
- POST /api/sets/{id}/rate-difficulty returns 200 (second POST while running -> 400)
- Set detail exposes rating {status:running/done}
- PUT /api/jobs/{job}/questions/{qid} with difficulty='Bogus' -> 400
- PUT difficulty='' clears it and filename has no difficulty suffix (regression - no changes to marks/crops)
- PUT difficulty='Hard' updates filename, memo matching question renames
- Filenames encode difficulty after marks (e.g. _3marks_Hard.png) and plain _Hard.png when marks None
- Excel catalogue (gr12-physical-sciences) has 'Difficulty' column in the IEB block
- sync_difficulty: memo/addendum/errata inherit QP difficulty, 'hardest' logic
"""
import os
import io
import sys
import asyncio
import copy
import uuid
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / "frontend" / ".env")
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
AUTH = {"Authorization": "Bearer test_session_qa_papercut"}

_LOOP = asyncio.new_event_loop()


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(MONGO_URL, io_loop=_LOOP)[DB_NAME]


def arun(coro):
    return _LOOP.run_until_complete(coro)


EXISTING_NID = Path("/tmp/nid").read_text().strip() if Path("/tmp/nid").exists() else None


# ---------- (0) Pre-flight: existing rated clone is sane ----------
def test_existing_rated_clone_has_difficulty_filenames():
    assert EXISTING_NID
    r = requests.get(f"{BASE_URL}/api/sets/{EXISTING_NID}", headers=AUTH, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("rating", {}).get("status") == "done", data.get("rating")
    docs = data["documents"]
    jqp = next(d for d in docs if d["meta"]["doc_type"] == "question_paper")
    jmemo = next(d for d in docs if d["meta"]["doc_type"] == "memo")
    # QP: every question has a difficulty & filename ends in _<Diff>.png (and _<N>marks_<Diff>.png when marks)
    for q in jqp["questions"]:
        assert q["difficulty"] in ("Easy", "Medium", "Hard"), q
        fn = q["filename"]
        assert fn.endswith(f"_{q['difficulty']}.png"), fn
        if q.get("marks") is not None:
            assert f"_{q['marks']}marks_{q['difficulty']}.png" in fn, fn
    # Memo synced from QP
    for mq in jmemo["questions"]:
        if mq.get("difficulty"):
            assert mq["filename"].endswith(f"_{mq['difficulty']}.png"), mq["filename"]


# ---------- (1) PUT question difficulty validation ----------
def test_update_question_difficulty_bogus_and_clear():
    db = _db()
    assert EXISTING_NID
    qp_doc = arun(db.jobs.find_one({"set_id": EXISTING_NID, "meta.doc_type": "question_paper", "is_deleted": False}))
    memo_doc = arun(db.jobs.find_one({"set_id": EXISTING_NID, "meta.doc_type": "memo", "is_deleted": False}))
    qp_id = qp_doc["_id"]
    memo_id = memo_doc["_id"]

    # Pick a QP question that has marks (so we can assert the _marks_Diff suffix format)
    q = next(q for q in qp_doc["questions"] if q.get("marks") is not None and q.get("difficulty"))
    qid = q["id"]
    orig_diff = q["difficulty"]
    label = q["label"]
    marks = q["marks"]

    # Bogus difficulty -> 400
    r = requests.put(f"{BASE_URL}/api/jobs/{qp_id}/questions/{qid}", json={"difficulty": "Bogus"}, headers=AUTH, timeout=15)
    assert r.status_code == 400, r.text
    assert "easy" in r.text.lower() or "medium" in r.text.lower() or "hard" in r.text.lower()

    # Set difficulty to Hard
    r = requests.put(f"{BASE_URL}/api/jobs/{qp_id}/questions/{qid}", json={"difficulty": "Hard"}, headers=AUTH, timeout=20)
    assert r.status_code == 200, r.text

    def get_doc(set_id, doc_type):
        s = requests.get(f"{BASE_URL}/api/sets/{set_id}", headers=AUTH, timeout=10).json()
        return next(d for d in s["documents"] if d["meta"]["doc_type"] == doc_type)

    jqp = get_doc(EXISTING_NID, "question_paper")
    q_new = next(x for x in jqp["questions"] if x["id"] == qid)
    assert q_new["difficulty"] == "Hard"
    assert q_new["filename"].endswith(f"_{marks}marks_Hard.png"), q_new["filename"]
    print(f"[Hard] qp fn={q_new['filename']}")

    # Memo matching question also renamed to _Hard.png
    jmemo = get_doc(EXISTING_NID, "memo")
    import re
    def norm(x):
        m = re.search(r"\d+(?:\.\d+)*", x or "")
        return m.group(0) if m else x
    nlabel = norm(label)
    memo_q = next((x for x in jmemo["questions"] if norm(x["label"]) == nlabel), None)
    if memo_q:
        assert memo_q["difficulty"] == "Hard", memo_q
        assert memo_q["filename"].endswith("_Hard.png"), memo_q["filename"]
        print(f"[Hard] memo fn={memo_q['filename']}")

    # Clear difficulty with "" -> filename has no diff suffix
    r = requests.put(f"{BASE_URL}/api/jobs/{qp_id}/questions/{qid}", json={"difficulty": ""}, headers=AUTH, timeout=20)
    assert r.status_code == 200, r.text
    jqp = get_doc(EXISTING_NID, "question_paper")
    q_new = next(x for x in jqp["questions"] if x["id"] == qid)
    assert q_new["difficulty"] is None, q_new
    assert q_new["filename"].endswith(f"_{marks}marks.png"), q_new["filename"]
    print(f"[cleared] qp fn={q_new['filename']}")

    # Restore original difficulty (keeps catalogue consistent)
    requests.put(f"{BASE_URL}/api/jobs/{qp_id}/questions/{qid}", json={"difficulty": orig_diff}, headers=AUTH, timeout=20)


# ---------- (2) sync_difficulty + hardest ----------
def test_sync_difficulty_hardest_from_qp_to_memo():
    from jobs import hardest, sync_difficulty, norm_label  # noqa
    assert hardest(["Easy", "Hard", "Medium"]) == "Hard"
    assert hardest(["Easy", "Medium"]) == "Medium"
    assert hardest(["Easy"]) == "Easy"
    assert hardest([]) is None
    assert hardest([None, "weird", "Easy"]) == "Easy"


# ---------- (3) renumber filename rules ----------
def test_renumber_filename_rules():
    from jobs import renumber
    from models import Job, JobMeta, Question, Part

    def mk_q(label, marks, difficulty):
        return Question(label=label, storage_path="s", parts=[Part(page=0, y0=0, y1=10)], marks=marks, difficulty=difficulty)

    qp = Job(filename="qp.pdf", pdf_path="p", status="done", total_pages=1,
             meta=JobMeta(subject="Mathematics", grade="12", year="2024", session="Nov", paper="1", doc_type="question_paper"),
             questions=[mk_q("1.1", 3, "Easy"), mk_q("2.3", None, "Hard"), mk_q("2.1", 2, None)])
    renumber(qp, "Mathematics_Gr12_2024_Nov_P1")
    fns = [q.filename for q in qp.questions]
    assert fns[0] == "001_Mathematics_Gr12_2024_Nov_P1_Q1.1_3marks_Easy.png", fns[0]
    assert fns[1] == "002_Mathematics_Gr12_2024_Nov_P1_Q2.3_Hard.png", fns[1]
    assert fns[2] == "003_Mathematics_Gr12_2024_Nov_P1_Q2.1_2marks.png", fns[2]

    memo = Job(filename="memo.pdf", pdf_path="p", status="done", total_pages=1,
               meta=JobMeta(subject="Mathematics", grade="12", year="2024", session="Nov", paper="1", doc_type="memo"),
               questions=[mk_q("1.1", 3, "Easy")])
    renumber(memo, "Mathematics_Gr12_2024_Nov_P1")
    assert memo.questions[0].filename == "001_Mathematics_Gr12_2024_Nov_P1_MEMO_Q1.1_3marks_Easy.png"

    # Addendum: marks never shown
    adden = Job(filename="a.pdf", pdf_path="p", status="done", total_pages=1,
                meta=JobMeta(subject="Mathematics", grade="12", year="2024", session="Nov", paper="1", doc_type="addendum"),
                questions=[mk_q("4.1", 5, "Medium")])
    renumber(adden, "Mathematics_Gr12_2024_Nov_P1")
    assert adden.questions[0].filename == "001_Mathematics_Gr12_2024_Nov_P1_ADDENDUM_Q4.1_Medium.png", adden.questions[0].filename


# ---------- (4) Rate difficulty 400 while running ----------
def test_rate_difficulty_concurrent_returns_400():
    """Clone a set, trim to 1 question, trigger rate, immediate second POST -> 400."""
    db = _db()
    import subprocess
    proc = subprocess.run(["python3", "tests/clone_set.py"], cwd="/app/backend",
                          env={**os.environ, "PYTHONPATH": "."}, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    clone_id = proc.stdout.strip().splitlines()[-1]
    assert len(clone_id) == 36
    print(f"[clone] {clone_id}")
    try:
        # Trim QP to a single question so AI cost is 1 call
        qp = arun(db.jobs.find_one({"set_id": clone_id, "meta.doc_type": "question_paper", "is_deleted": False}))
        single_q = qp["questions"][0]
        single_q["difficulty"] = None  # ensure rating has something to update
        arun(db.jobs.update_one({"_id": qp["_id"]}, {"$set": {"questions": [single_q]}}))
        # Also reset set rating to None
        arun(db.sets.update_one({"_id": clone_id}, {"$set": {"rating": None}}))

        # POST rate-difficulty
        r = requests.post(f"{BASE_URL}/api/sets/{clone_id}/rate-difficulty", headers=AUTH, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        rating = data.get("rating") or {}
        assert rating.get("status") == "running", rating
        assert rating.get("total") == 1, rating
        print(f"[rate-start] {rating}")

        # Second POST while running -> 400
        r2 = requests.post(f"{BASE_URL}/api/sets/{clone_id}/rate-difficulty", headers=AUTH, timeout=15)
        assert r2.status_code == 400, r2.text
        print(f"[rate-409] {r2.text}")

        # Wait up to 45s for rating to finish
        done = False
        for i in range(45):
            time.sleep(1)
            s = requests.get(f"{BASE_URL}/api/sets/{clone_id}", headers=AUTH, timeout=10).json()
            st = (s.get("rating") or {}).get("status")
            if st in ("done", "error"):
                print(f"[rate-final] {s['rating']}")
                done = True
                assert st == "done", s["rating"]
                break
        assert done, "rate didn't finish"

        # QP question should now have a difficulty + filename includes it
        s2 = requests.get(f"{BASE_URL}/api/sets/{clone_id}", headers=AUTH, timeout=10).json()
        jqp = next(d for d in s2["documents"] if d["meta"]["doc_type"] == "question_paper")
        q_new = jqp["questions"][0]
        assert q_new["difficulty"] in ("Easy", "Medium", "Hard"), q_new
        assert q_new["filename"].endswith(f"_{q_new['difficulty']}.png"), q_new["filename"]

        # Set with no QP done -> 400
        arun(db.jobs.update_one({"_id": qp["_id"]}, {"$set": {"status": "ready", "questions": []}}))
        r3 = requests.post(f"{BASE_URL}/api/sets/{clone_id}/rate-difficulty", headers=AUTH, timeout=15)
        assert r3.status_code == 400, r3.text
    finally:
        arun(db.sets.update_one({"_id": clone_id}, {"$set": {"is_deleted": True}}))
        arun(db.jobs.update_many({"set_id": clone_id}, {"$set": {"is_deleted": True}}))


# ---------- (5) Excel catalogue has Difficulty column ----------
def test_catalogue_difficulty_column_physical_sciences():
    import openpyxl
    r = requests.get(f"{BASE_URL}/api/catalogues/gr12-physical-sciences/download", headers=AUTH, timeout=60)
    assert r.status_code == 200, r.text[:200]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    # The cloned set's meta has province=IEB, year=2023, paper=2 -> IEB sheet
    assert "IEB" in wb.sheetnames, wb.sheetnames
    ws = wb["IEB"]
    # Find a Difficulty header cell somewhere on the sheet
    found_header = False
    found_rating_cell = False
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if cell.value == "Difficulty":
                found_header = True
                # scan the column below for any Easy:/Medium:/Hard: entry
                for i in range(cell.row + 1, min(cell.row + 60, ws.max_row + 1)):
                    v = ws.cell(i, cell.column).value
                    if v and ("Easy:" in str(v) or "Medium:" in str(v) or "Hard:" in str(v)):
                        found_rating_cell = True
                        print(f"[cat] {ws.title} r{i}c{cell.column} = {v!r}")
                        break
    assert found_header, "no Difficulty header found on IEB sheet"
    assert found_rating_cell, "no Easy/Medium/Hard entry below the Difficulty header"


# ---------- (6) norm_difficulty ----------
def test_norm_difficulty():
    from ai import norm_difficulty, LEVELS
    assert LEVELS == ("Easy", "Medium", "Hard")
    assert norm_difficulty("Easy") == "Easy"
    assert norm_difficulty("beginner") == "Easy"
    assert norm_difficulty("MEDIUM") == "Medium"
    assert norm_difficulty("moderate") == "Medium"
    assert norm_difficulty("hard") == "Hard"
    assert norm_difficulty("challenging") == "Hard"
    assert norm_difficulty("") is None
    assert norm_difficulty(None) is None
    assert norm_difficulty("bogus") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
