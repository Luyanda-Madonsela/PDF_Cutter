import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive import question_folder_name
from models import Question


def test_numeric_question_folder_keeps_its_question_label():
    questions = [
        Question(label="1.1", storage_path="q1.png", order=1),
        Question(label="1.2", storage_path="q2.png", order=2),
    ]

    assert question_folder_name(questions[0], questions) == "Question_1.1"
    assert question_folder_name(questions[1], questions) == "Question_1.2"


def test_lettered_question_folder_keeps_parent_question_number():
    questions = [
        Question(label="1.1", storage_path="q1.png", order=1),
        Question(label="(a)", storage_path="qa.png", order=2),
        Question(label="(b)", storage_path="qb.png", order=3),
    ]

    assert question_folder_name(questions[1], questions) == "Question_1_(a)"
    assert question_folder_name(questions[2], questions) == "Question_1_(b)"
