"""End-to-end tests of Mistral OCR through Mistral's API.

Skipped by default. Run them with a key:

    MISTRAL_API_KEY=... pytest -m live -n 8 tests/test_live_mistral.py

A full run reads every sample page once (about 10 cents).
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from urllib.parse import unquote

import pytest

from docs_to_md import cli

from .conftest import CapturingConsole
from .samples import SAMPLES

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MISTRAL_API_KEY"), reason="set MISTRAL_API_KEY to run live tests"),
]

PAGE_MARKER = re.compile(r"^\{(\d+)\}-{48}$", re.MULTILINE)


def normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def convert(tmp_path, sample, *args):
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    argv = [str(source), "-o", str(tmp_path / "out"), "--backend", "mistral", *args]
    code = cli.main(argv, console=console)
    assert code == 0, console.err
    return tmp_path / "out", console


@pytest.mark.parametrize("sample", SAMPLES, ids=[s.filename for s in SAMPLES])
def test_markdown_ocr(tmp_path, sample):
    # One page per chunk exercises splitting, merging, and page renumbering.
    out, console = convert(tmp_path, sample, "--chunk-size", "1", "--paginate")
    text = (out / sample.filename.replace(".pdf", ".md")).read_text(encoding="utf-8")

    for keyword in sample.keywords:
        assert normalized(keyword) in normalized(text), f"{keyword!r} missing"
    assert [int(n) for n in PAGE_MARKER.findall(text)] == list(range(sample.pages))
    assert sum(line.startswith("|") for line in text.splitlines()) >= sample.min_table_rows
    for link in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert (out / unquote(link)).is_file(), f"broken image link {link}"
    assert f"{sample.pages} page" in console.err
    assert "$" in console.err  # the cost is reported


def test_running_headers_are_left_out(tmp_path):
    sample = next(s for s in SAMPLES if s.language == "de")
    out, _ = convert(tmp_path, sample)
    text = (out / sample.filename.replace(".pdf", ".md")).read_text(encoding="utf-8")
    assert "Digitized by Google" not in text


def test_rejected_api_key_exits_with_usage_error(tmp_path):
    sample = SAMPLES[1]
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    args = [str(source), "--backend", "mistral", "--api-key", "definitely-not-a-valid-key"]
    assert cli.main(args, console=console) == cli.EXIT_USAGE
    assert "Authentication failed" in console.err
