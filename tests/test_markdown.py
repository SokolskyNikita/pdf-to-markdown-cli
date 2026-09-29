import pytest

from docs_to_md.markdown import normalize_line_breaks, remove_duplicate_captions

LINE_A = "This is a long paragraph line that was wrapped by OCR output even though it should stay"
LINE_B = "as one paragraph because the sentence continues naturally on the next line."


def test_merges_wrapped_paragraph_lines():
    assert normalize_line_breaks(f"{LINE_A}\n{LINE_B}\n") == f"{LINE_A} {LINE_B}\n"


def test_preserves_missing_trailing_newline():
    assert normalize_line_breaks(f"{LINE_A}\n{LINE_B}") == f"{LINE_A} {LINE_B}"


def test_paragraphs_stay_separate():
    text = f"{LINE_A}\n{LINE_B}\n\n{LINE_A}\n{LINE_B}\n"
    assert normalize_line_breaks(text) == f"{LINE_A} {LINE_B}\n\n{LINE_A} {LINE_B}\n"


@pytest.mark.parametrize(
    "text",
    [
        "- First list entry that should stay on its own line\n- Second list entry that should remain\n",
        "1. First numbered entry that should stay on its own line\n2. Second numbered entry\n",
        "```python\nprint('hello there, this is a long line of code')\nprint('world')\n```\n",
        "This line intentionally uses a markdown hard break.  \nSecond line should remain separate.\n",
        "Name\nRole\nTeam\n",
        "| a long table cell with plenty of text | b |\n| another long table cell here | d |\n",
        "> quoted text that is long enough to count as prose for the heuristic\n> more quoted\n",
        "$$\nx = \\frac{a very long numerator expression here}{another long denominator}\n$$\n",
        "The first sentence of this block ends with a period.\nThe second sentence also ends properly.\n",
        "",
    ],
)
def test_leaves_structure_unchanged(text):
    assert normalize_line_breaks(text) == text


def test_indented_code_is_not_joined():
    text = f"    {LINE_A}\n    {LINE_B}\n"
    assert normalize_line_breaks(text) == text


def test_duplicate_image_caption_paragraph_is_removed():
    text = "![A diagram of a tree](img.jpg)\n\nA diagram of a tree\n\nA real caption.\n"
    assert remove_duplicate_captions(text) == "![A diagram of a tree](img.jpg)\n\nA real caption.\n"


def test_distinct_caption_is_kept():
    text = "![A diagram](img.jpg)\n\nFigure 1: Tree of life\n"
    assert remove_duplicate_captions(text) == text
