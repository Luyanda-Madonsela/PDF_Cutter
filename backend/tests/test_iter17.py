"""Iteration 17: Manual difficulty picker in Adjust crop tab.

Covers:
- PUT /api/jobs/{qp_job}/questions/{qid} with difficulty=Hard updates QP + syncs memo.
- PUT /api/jobs/{memo_job}/questions/{qid} with difficulty=Easy updates MATCHING QP question
  (and renames) - set_qp_difficulty behavior.
- Memo label that corresponds to a QP main (sub-labels) propagates to all QP children.
- 400 "No Qx in the question paper to rate" when no QP label matches.
"""
import os
import re
import sys
import asyncio
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

NID = Path("/tmp/nid").read_text().strip()

_LOOP = asyncio.new_event_loop()


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(MONGO_URL, io_loop=_LOOP)[DB_NAME]


def arun(coro):
    return _LOOP.run_until_complete(coro)


def _norm(s):
    m = re.search(r"\d+(?:\.\d+)*", s or "")
    return m.group(0) if m else s


def _set():
    r = requests.get(f"{BASE_URL}/api/sets/{NID}", headers=AUTH, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _docs(data):
    qp = next(d for d in data["documents"] if d["meta"]["doc_type"] == "question_paper")
    memo = next((d for d in data["documents"] if d["meta"]["doc_type"] == "memo"), None)
    return qp, memo


# ---------- (1) QP tab: setting Hard renames QP + memo matching question ----------
def test_qp_adjust_set_hard_syncs_memo():
    data = _set()
    qp, memo = _docs(data)
    assert memo
    # pick QP question that has a memo match and marks
    memo_labels = {_norm(m["label"]) for m in memo["questions"]}
    q = None
    for cand in qp["questions"]:
        if cand.get("marks") is not None and _norm(cand["label"]) in memo_labels:
            q = cand; break
    assert q, "no QP question with marks and memo match found"
    qid = q["id"]
    orig = q["difficulty"]
    marks = q["marks"]
    lbl = q["label"]
    try:
        r = requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{qid}",
                         json={"difficulty": "Hard"}, headers=AUTH, timeout=20)
        assert r.status_code == 200, r.text
        data2 = _set()
        qp2, memo2 = _docs(data2)
        q2 = next(x for x in qp2["questions"] if x["id"] == qid)
        assert q2["difficulty"] == "Hard"
        assert q2["filename"].endswith(f"_{marks}marks_Hard.png"), q2["filename"]
        mq = next((x for x in memo2["questions"] if _norm(x["label"]) == _norm(lbl)), None)
        assert mq, "memo match disappeared"
        assert mq["difficulty"] == "Hard", mq
        assert mq["filename"].endswith("_Hard.png"), mq["filename"]
    finally:
        requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{qid}",
                     json={"difficulty": orig or ""}, headers=AUTH, timeout=20)


# ---------- (2) Memo tab: setting difficulty updates matching QP question ----------
def test_memo_adjust_set_easy_updates_matching_qp():
    data = _set()
    qp, memo = _docs(data)
    assert memo
    qp_labels = {_norm(q["label"]): q for q in qp["questions"]}
    # pick a memo question whose exact norm label is in QP (leaf match)
    mq = None
    for cand in memo["questions"]:
        if _norm(cand["label"]) in qp_labels:
            mq = cand; break
    assert mq, "no leaf memo->QP match found"
    qp_match = qp_labels[_norm(mq["label"])]
    orig = qp_match["difficulty"]
    try:
        r = requests.put(f"{BASE_URL}/api/jobs/{memo['id']}/questions/{mq['id']}",
                         json={"difficulty": "Easy"}, headers=AUTH, timeout=20)
        assert r.status_code == 200, r.text
        data2 = _set()
        qp2, memo2 = _docs(data2)
        qp_q2 = next(x for x in qp2["questions"] if x["id"] == qp_match["id"])
        assert qp_q2["difficulty"] == "Easy", qp_q2
        mq2 = next(x for x in memo2["questions"] if x["id"] == mq["id"])
        assert mq2["difficulty"] == "Easy", mq2
        assert mq2["filename"].endswith("_Easy.png"), mq2["filename"]
        assert "_Easy.png" in qp_q2["filename"], qp_q2["filename"]
    finally:
        requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{qp_match['id']}",
                     json={"difficulty": orig or ""}, headers=AUTH, timeout=20)


# ---------- (3) Memo main label propagates to all QP sub-labels ----------
def test_memo_main_label_propagates_to_sub_questions():
    """If memo has e.g. '4' and QP has '4.1' and '4.2', setting difficulty on memo '4'
    should update both QP children."""
    data = _set()
    qp, memo = _docs(data)
    assert memo
    qp_norms = [_norm(q["label"]) for q in qp["questions"]]
    # find a memo question whose norm is a prefix for 2+ QP labels (and norm not an exact match)
    target = None
    for cand in memo["questions"]:
        n = _norm(cand["label"])
        if n in qp_norms:
            continue
        children = [q for q, qn in zip(qp["questions"], qp_norms) if qn.startswith(n + ".")]
        if len(children) >= 2:
            target = (cand, children); break
    if not target:
        pytest.skip("no memo main label with 2+ QP sub-children in this clone")
    mq, children = target
    origs = {c["id"]: c["difficulty"] for c in children}
    try:
        r = requests.put(f"{BASE_URL}/api/jobs/{memo['id']}/questions/{mq['id']}",
                         json={"difficulty": "Medium"}, headers=AUTH, timeout=20)
        assert r.status_code == 200, r.text
        data2 = _set()
        qp2, _ = _docs(data2)
        for c in children:
            q2 = next(x for x in qp2["questions"] if x["id"] == c["id"])
            assert q2["difficulty"] == "Medium", q2
    finally:
        for cid, orig in origs.items():
            requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{cid}",
                         json={"difficulty": orig or ""}, headers=AUTH, timeout=20)


# ---------- (4) Memo label with no QP match -> 400 ----------
def test_memo_no_qp_match_returns_400():
    """Temporarily change a memo question's label to one that doesn't exist in QP,
    then try to set difficulty via memo -> should 400."""
    db = _db()
    memo_doc = arun(db.jobs.find_one({"set_id": NID, "meta.doc_type": "memo", "is_deleted": False}))
    qp_doc = arun(db.jobs.find_one({"set_id": NID, "meta.doc_type": "question_paper", "is_deleted": False}))
    qp_norms = {_norm(q["label"]) for q in qp_doc["questions"]}
    # Pick any memo question
    target = memo_doc["questions"][0]
    orig_label = target["label"]
    # Craft a bogus label that definitely doesn't match any QP leaf or prefix
    bogus = "99.99"
    assert bogus not in qp_norms and not any(n.startswith(bogus + ".") for n in qp_norms)
    try:
        arun(db.jobs.update_one(
            {"_id": memo_doc["_id"], "questions.id": target["id"]},
            {"$set": {"questions.$.label": bogus}}))
        r = requests.put(f"{BASE_URL}/api/jobs/{memo_doc['_id']}/questions/{target['id']}",
                         json={"difficulty": "Hard"}, headers=AUTH, timeout=20)
        assert r.status_code == 400, r.text
        assert "No Q" in r.text and "rate" in r.text, r.text
    finally:
        arun(db.jobs.update_one(
            {"_id": memo_doc["_id"], "questions.id": target["id"]},
            {"$set": {"questions.$.label": orig_label}}))


# ---------- (5) QP picker: clearing memo stays idempotent via QP side ----------
def test_qp_picker_matches_LEVELS_and_rejects_bogus():
    data = _set()
    qp, _ = _docs(data)
    q = qp["questions"][0]
    r = requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{q['id']}",
                     json={"difficulty": "beginner"}, headers=AUTH, timeout=10)
    assert r.status_code == 400, r.text  # case-sensitive LEVELS check
    for lvl in ("Easy", "Medium", "Hard"):
        r = requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{q['id']}",
                         json={"difficulty": lvl}, headers=AUTH, timeout=15)
        assert r.status_code == 200, (lvl, r.text)
    # restore
    requests.put(f"{BASE_URL}/api/jobs/{qp['id']}/questions/{q['id']}",
                 json={"difficulty": q["difficulty"] or ""}, headers=AUTH, timeout=15)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
