"""End-to-end tests against the real Datalab API.

Skipped by default. Run them with a key when changing anything that affects
conversion output:

    DATALAB_API_KEY=... pytest -m live -n 8

A full run converts about 25 pages (a few cents).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from urllib.parse import unquote

import pytest

from docs_to_md import cli

from .conftest import CapturingConsole
from .samples import SAMPLES

API_KEY = os.environ.get("DATALAB_API_KEY") or os.environ.get("MARKER_PDF_KEY")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not API_KEY, reason="set DATALAB_API_KEY to run live API tests"),
]

PAGE_MARKER = re.compile(r"^\{(\d+)\}-{48}$", re.MULTILINE)


def convert(tmp_path, sample, *args):
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    code = cli.main([str(source), "-o", str(tmp_path / "out"), *args], console=console)
    assert code == 0, console.err
    return tmp_path / "out", console


@pytest.mark.parametrize("sample", SAMPLES, ids=[s.filename for s in SAMPLES])
def test_markdown_conversion(tmp_path, sample):
    # One page per chunk exercises splitting, merging, and page renumbering.
    mode = ["--mode", sample.mode] if sample.mode else []
    out, console = convert(tmp_path, sample, "--chunk-size", "1", "--paginate", *mode)
    text = (out / sample.filename.replace(".pdf", ".md")).read_text(encoding="utf-8")

    for keyword in sample.keywords:
        assert keyword.casefold() in text.casefold(), f"{keyword!r} missing"
    assert [int(n) for n in PAGE_MARKER.findall(text)] == list(range(sample.pages))
    assert sum(line.startswith("|") for line in text.splitlines()) >= sample.min_table_rows
    for link in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert (out / unquote(link)).is_file(), f"broken image link {link}"
    assert f"{sample.pages} page" in console.err


def test_html_conversion_merges_chunks(tmp_path):
    sample = next(s for s in SAMPLES if s.language == "ru")
    out, _ = convert(tmp_path, sample, "--html", "--chunk-size", "1", "--paginate")
    html = (out / sample.filename.replace(".pdf", ".html")).read_text(encoding="utf-8")
    assert html.count("<body") == 1
    assert re.findall(r'data-page-id="(\d+)"', html) == ["0", "1"]
    assert "vicomte" in html


def test_json_conversion_merges_chunks(tmp_path):
    sample = next(s for s in SAMPLES if s.language == "de")
    out, _ = convert(tmp_path, sample, "--json", "--chunk-size", "1")
    data = json.loads((out / sample.filename.replace(".pdf", ".json")).read_text(encoding="utf-8"))
    assert [child["id"] for child in data["children"]] == ["/page/0/Page/0", "/page/1/Page/0"]


def test_rejected_api_key_exits_with_usage_error(tmp_path):
    sample = SAMPLES[1]
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    code = cli.main([str(source), "--api-key", "definitely-not-a-valid-key"], console=console)
    assert code == cli.EXIT_USAGE
    assert "Authentication failed" in console.err
