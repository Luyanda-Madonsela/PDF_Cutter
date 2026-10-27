import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import cut_bands
from imaging import magic_erase
from jobs import merge_groups
from PIL import Image, ImageDraw


def test_far_below_marks_are_stitched_after_answer_space_is_removed():
    question_and_marks = {
        "label": "1.1",
        "y0": 100,
        "y1": 700,
        "marks": 5,
        "review": None,
        "topic": None,
        "difficulty": None,
        "group_with_previous": False,
    }

    segments = cut_bands([question_and_marks], [(240, 620)])
    groups = merge_groups([segments])

    assert [(part.y0, part.y1) for part in groups[0]["parts"]] == [(100, 240), (620, 700)]
    assert groups[0]["marks"] == [5, None]


def test_white_out_boxes_replace_black_space_with_white():
    image = Image.new("RGB", (100, 100), "black")
    ImageDraw.Draw(image).rectangle((20, 20, 79, 79), fill="black")

    result = magic_erase(image, [], [[200, 200, 800, 800]])

    assert result.getpixel((50, 50)) == (255, 255, 255)
    assert result.getpixel((10, 10)) == (0, 0, 0)
