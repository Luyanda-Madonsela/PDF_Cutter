import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import routes
from jobs import compute_links
from models import Job, JobMeta, MemoLinkUpdate, Part, Question


def test_manual_memo_link_overrides_automatic_label_matching():
    question = Question(label="2.1", storage_path="question.png", memo_links=["memo-b"])
    qp = Job(filename="paper.pdf", status="done", meta=JobMeta(doc_type="question_paper"), questions=[question])
    memo = Job(
        filename="memo.pdf",
        status="done",
        meta=JobMeta(doc_type="memo"),
        questions=[
            Question(id="memo-a", label="2.1", storage_path="memo-a.png"),
            Question(id="memo-b", label="4.1", storage_path="memo-b.png"),
        ],
    )

    links = compute_links([qp, memo])

    assert [ref["qid"] for ref in links["links"][question.id]["memos"]] == ["memo-b"]
    assert [ref["qid"] for ref in links["extras"]["memo_unmatched"]] == ["memo-a"]


def test_human_can_save_a_manual_memo_link(monkeypatch):
    question = Question(id="question-1", label="2.1", storage_path="question.png")
    qp = Job(
        id="paper-job",
        filename="paper.pdf",
        set_id="set-1",
        status="done",
        meta=JobMeta(doc_type="question_paper"),
        questions=[question],
    )
    memo = Job(
        id="memo-job",
        filename="memo.pdf",
        set_id="set-1",
        status="done",
        meta=JobMeta(doc_type="memo"),
        questions=[Question(id="memo-answer", label="4.1", storage_path="memo.png")],
    )

    async def load_job(_job_id):
        return qp

    async def load_set_jobs(_set_id):
        return [qp, memo]

    async def return_updated_job(job, _set_id):
        return job

    monkeypatch.setattr(routes, "job_or_404", load_job)
    monkeypatch.setattr(routes, "set_jobs", load_set_jobs)
    monkeypatch.setattr(routes, "edit_and_return", return_updated_job)

    result = asyncio.run(
        routes.update_memo_links("paper-job", "question-1", MemoLinkUpdate(memo_qids=["memo-answer"]))
    )

    assert result.questions[0].memo_links == ["memo-answer"]
    assert compute_links([qp, memo])["links"]["question-1"]["memo"]["qid"] == "memo-answer"


def test_human_cannot_link_a_question_to_a_memo_outside_its_set(monkeypatch):
    question = Question(id="question-1", label="2.1", storage_path="question.png")
    qp = Job(
        id="paper-job",
        filename="paper.pdf",
        set_id="set-1",
        status="done",
        meta=JobMeta(doc_type="question_paper"),
        questions=[question],
    )

    async def load_job(_job_id):
        return qp

    async def load_set_jobs(_set_id):
        return [qp]

    monkeypatch.setattr(routes, "job_or_404", load_job)
    monkeypatch.setattr(routes, "set_jobs", load_set_jobs)

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(
            routes.update_memo_links("paper-job", "question-1", MemoLinkUpdate(memo_qids=["outside"]))
        )
    assert error.value.status_code == 400


@pytest.mark.parametrize("manual_link", [False, True])
def test_merge_combines_non_adjacent_memo_answers_and_preserves_manual_links(monkeypatch, manual_link):
    question_a = Question(
        id="question-a",
        label="2.1",
        storage_path="question-a.png",
        parts=[Part(page=0, y0=10, y1=20)],
        memo_links=["memo-a"] if manual_link else [],
    )
    question_b = Question(
        id="question-b",
        label="2.2",
        storage_path="question-b.png",
        parts=[Part(page=0, y0=30, y1=40)],
    )
    qp = Job(
        id="paper-job",
        filename="paper.pdf",
        set_id="set-1",
        status="done",
        meta=JobMeta(doc_type="question_paper"),
        questions=[question_a, question_b],
    )
    memo_a = Question(
        id="memo-a",
        label="2.1",
        storage_path="memo-a.png",
        parts=[Part(page=0, y0=10, y1=20)],
    )
    memo_unrelated = Question(
        id="memo-unrelated",
        label="4.1",
        storage_path="memo-unrelated.png",
        parts=[Part(page=0, y0=30, y1=40)],
    )
    memo_b = Question(
        id="memo-b",
        label="2.2",
        storage_path="memo-b.png",
        parts=[Part(page=0, y0=50, y1=60)],
    )
    memo = Job(
        id="memo-job",
        filename="memo.pdf",
        set_id="set-1",
        status="done",
        meta=JobMeta(doc_type="memo"),
        questions=[memo_a, memo_unrelated, memo_b],
    )

    async def load_job(_job_id):
        return qp

    async def load_set_jobs(_set_id):
        return [qp, memo]

    async def get_pdf(_path):
        return b"pdf"

    async def rebuild_question(job, _doc, label, parts, marks, flags, qid, **kwargs):
        previous = next(question for question in job.questions if question.id == qid)
        return Question(
            id=qid,
            label=label,
            related_labels=kwargs.get("related_labels") or [label],
            filename=previous.filename,
            storage_path=f"{qid}-merged.png",
            parts=parts,
            marks=marks,
            flags=flags,
            memo_links=kwargs.get("memo_links") or [],
        )

    class FakePdf:
        page_count = 1

        def close(self):
            pass

    async def return_updated_job(job, _set_id):
        return job

    monkeypatch.setattr(routes, "job_or_404", load_job)
    monkeypatch.setattr(routes, "set_jobs", load_set_jobs)
    monkeypatch.setattr(routes, "get_object", get_pdf)
    monkeypatch.setattr(routes, "rebuild_question", rebuild_question)
    monkeypatch.setattr(routes, "save_linked", lambda *_args: asyncio.sleep(0))
    monkeypatch.setattr(routes, "edit_and_return", return_updated_job)
    monkeypatch.setattr(routes.pymupdf, "open", lambda **_kwargs: FakePdf())

    result = asyncio.run(routes.merge_next("paper-job", "question-a"))

    assert len(result.questions) == 1
    assert result.questions[0].memo_links == (["memo-a"] if manual_link else [])
    assert [question.id for question in memo.questions] == ["memo-a", "memo-unrelated"]
    assert [(part.y0, part.y1) for part in memo.questions[0].parts] == [(10, 20), (50, 60)]
    links = compute_links([qp, memo])["links"][question_a.id]
    assert [ref["qid"] for ref in links["memos"]] == ["memo-a"]
