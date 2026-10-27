import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import routes
from jobs import split_parts
from models import Job, JobMeta, Part, Question, QuestionSplit


def test_split_parts_splits_a_crop_region_on_one_page():
    first, second = split_parts([Part(page=0, y0=100, y1=900)], page=0, y=450)

    assert [(part.page, part.y0, part.y1) for part in first] == [(0, 100, 450)]
    assert [(part.page, part.y0, part.y1) for part in second] == [(0, 450, 900)]


def test_split_parts_partitions_regions_across_multiple_pages():
    parts = [
        Part(page=0, y0=100, y1=700),
        Part(page=1, y0=50, y1=600),
        Part(page=2, y0=200, y1=800),
    ]

    first, second = split_parts(parts, page=1, y=300)

    assert [(part.page, part.y0, part.y1) for part in first] == [(0, 100, 700), (1, 50, 300)]
    assert [(part.page, part.y0, part.y1) for part in second] == [(1, 300, 600), (2, 200, 800)]


@pytest.mark.parametrize("y", [100, 900])
def test_split_parts_rejects_boundary_of_crop(y):
    with pytest.raises(ValueError, match="inside exactly one crop region"):
        split_parts([Part(page=0, y0=100, y1=900)], page=0, y=y)


def test_split_parts_rejects_split_without_regions_on_both_sides():
    with pytest.raises(ValueError, match="inside exactly one crop region"):
        split_parts([Part(page=0, y0=100, y1=900)], page=1, y=450)


def test_split_question_unlinks_the_new_label_from_a_grouped_question(monkeypatch):
    question = Question(
        id="question-1",
        label="1.1",
        related_labels=["1.1", "1.2"],
        parts=[Part(page=0, y0=100, y1=900)],
        marks=12,
        storage_path="original.png",
    )
    job = Job(
        id="job-1",
        filename="paper.pdf",
        pdf_path="paper.pdf",
        status="done",
        total_pages=1,
        meta=JobMeta(doc_type="question_paper"),
        questions=[question],
    )

    async def load_job(_job_id):
        return job

    async def get_pdf(_path):
        return b"pdf"

    async def rebuild(_job, _doc, label, parts, marks, flags, qid, **kwargs):
        return Question(
            id=qid or f"{label}-id",
            label=label,
            related_labels=kwargs.get("related_labels") or [label],
            parts=parts,
            marks=marks,
            flags=flags,
            storage_path=f"{label}.png",
        )

    async def return_job(updated_job, _set_id):
        return updated_job

    class MockDocument:
        def close(self):
            pass

    monkeypatch.setattr(routes, "job_or_404", load_job)
    monkeypatch.setattr(routes, "get_object", get_pdf)
    monkeypatch.setattr(routes, "rebuild_question", rebuild)
    monkeypatch.setattr(routes, "edit_and_return", return_job)
    monkeypatch.setattr(routes.pymupdf, "open", lambda **_kwargs: MockDocument())

    result = asyncio.run(
        routes.split_question(
            "job-1",
            "question-1",
            QuestionSplit(page=0, y=500, label="1.2", parts=[Part(page=0, y0=50, y1=950)]),
        )
    )

    assert len(result.questions) == 2
    assert result.questions[0].related_labels == ["1.1"]
    assert result.questions[0].marks == 12
    assert result.questions[1].label == "1.2"
    assert result.questions[1].marks is None
    assert [(part.y0, part.y1) for part in result.questions[0].parts] == [(50, 500)]
    assert [(part.y0, part.y1) for part in result.questions[1].parts] == [(500, 950)]
