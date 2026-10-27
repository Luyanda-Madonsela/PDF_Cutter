import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import db
from drive import paper_folder
from jobs import compatible, compute_links, merge_groups, next_school_test_number, related_school_test_number
from models import DocSummary, Job, JobMeta, PaperSet, Question


def test_school_paper_drive_path_includes_test_number_and_language():
    meta = JobMeta(subject="Mathematics", grade="10", year="2026", school="Example School", language="Afrikaans")
    assert paper_folder(meta, ["Papers"], 3) == [
        "Papers", "2026", "Grade 10", "Mathematics", "Misc", "Example School", "Test_03", "Afrikaans"
    ]


def test_school_test_numbers_increment_per_school_scope():
    meta = JobMeta(school=f"Counter School {uuid.uuid4()}", year="2026", grade="10", subject="Mathematics")

    async def allocate():
        return await next_school_test_number(meta), await next_school_test_number(meta)

    assert asyncio.run(allocate()) == (1, 2)


def test_english_and_afrikaans_are_separate_but_share_school_test_number():
    english = JobMeta(subject="Mathematics", grade="10", year="2026", school="Example School", language="English")
    afrikaans = english.model_copy(update={"language": "Afrikaans"})
    assert not compatible(english, afrikaans)

    set_id = str(uuid.uuid4())
    paper_set = PaperSet(
        id=set_id,
        mode="bulk",
        meta=english,
        school_test_number=7,
        docs=[DocSummary(job_id="paper", doc_type="question_paper", filename="paper.pdf", status="done")],
    )

    async def store_and_find():
        await db.sets.insert_one(paper_set.to_mongo())
        try:
            return await related_school_test_number(afrikaans)
        finally:
            await db.sets.delete_one({"_id": set_id})

    assert asyncio.run(store_and_find()) == 7


def test_question_annotations_default_to_separate_overlay_metadata():
    question = Question(label="1.1", storage_path="overlay-test")
    question.annotations = [{"type": "text", "x": 0.25, "y": 0.5, "text": "Check units", "color": "#e11d48"}]
    serialized = question.model_dump()
    assert serialized["annotations"][0]["text"] == "Check units"
    assert serialized["storage_path"] == "overlay-test"


def test_shared_context_and_hence_segments_stay_in_one_question_image():
    groups = merge_groups([[
        {"label": "1.1", "y0": 100, "y1": 300, "marks": 2},
        {"label": "1.2", "y0": 310, "y1": 500, "marks": 3, "group_with_previous": True},
        {"label": "1.3", "y0": 510, "y1": 650, "marks": 1},
        {"label": "1.4", "y0": 660, "y1": 800, "marks": 2, "group_with_previous": True},
    ]])

    assert [group["related_labels"] for group in groups] == [["1.1", "1.2"], ["1.3", "1.4"]]
    assert [[(part.y0, part.y1) for part in group["parts"]] for group in groups] == [
        [(100, 300), (310, 500)],
        [(510, 650), (660, 800)],
    ]


def test_combined_question_image_keeps_each_memo_answer_linked():
    question = Question(label="1.1", related_labels=["1.1", "1.2"], storage_path="question.png")
    qp = Job(filename="paper.pdf", status="done", meta=JobMeta(doc_type="question_paper"), questions=[question])
    memo = Job(filename="memo.pdf", status="done", meta=JobMeta(doc_type="memo"), questions=[
        Question(label="1.1", storage_path="memo-1.png"),
        Question(label="1.2", storage_path="memo-2.png"),
    ])

    links = compute_links([qp, memo])["links"][question.id]

    assert [ref["qid"] for ref in links["memos"]] == [q.id for q in memo.questions]
    assert links["memo"] == links["memos"][0]
