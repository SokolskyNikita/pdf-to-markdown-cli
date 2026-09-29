"""End-to-end tests of GPT-Luna through OpenAI and through OpenRouter.

Skipped by default. Each backend runs when its key is set:

    OPENAI_API_KEY=... OPENROUTER_API_KEY=... pytest -m live tests/test_live_llm.py

A full run transcribes every sample page once per backend (a few cents each).
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata

import pytest

from docs_to_md import cli

from .conftest import CapturingConsole
from .samples import SAMPLES

pytestmark = pytest.mark.live

PAGE_MARKER = re.compile(r"^\{(\d+)\}-{48}$", re.MULTILINE)
BACKENDS = [
    pytest.param(
        name,
        marks=pytest.mark.skipif(not os.environ.get(env), reason=f"set {env} to run live {name} tests"),
        id=name,
    )
    for name, env in (("openai", "OPENAI_API_KEY"), ("openrouter", "OPENROUTER_API_KEY"))
]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def convert(tmp_path, sample, *args):
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    code = cli.main([str(source), "-o", str(tmp_path / "out"), *args], console=console)
    assert code == 0, console.err
    return tmp_path / "out", console


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("sample", SAMPLES, ids=[s.filename for s in SAMPLES])
def test_markdown_transcription(tmp_path, backend, sample):
    # One page per chunk exercises splitting, merging, and page renumbering.
    out, console = convert(tmp_path, sample, "--backend", backend, "--chunk-size", "1", "--paginate")
    text = (out / sample.filename.replace(".pdf", ".md")).read_text(encoding="utf-8")

    for keyword in sample.keywords:
        assert normalized(keyword) in normalized(text), f"{keyword!r} missing"
    assert [int(n) for n in PAGE_MARKER.findall(text)] == list(range(sample.pages))
    assert sum(line.startswith("|") for line in text.splitlines()) >= sample.min_table_rows
    assert f"{sample.pages} page" in console.err
    assert "$" in console.err  # the cost is reported


@pytest.mark.parametrize("backend", BACKENDS)
def test_html_transcription_merges_chunks(tmp_path, backend):
    sample = next(s for s in SAMPLES if s.language == "ru")
    out, _ = convert(tmp_path, sample, "--backend", backend, "--html", "--chunk-size", "1")
    html = (out / sample.filename.replace(".pdf", ".html")).read_text(encoding="utf-8")
    assert html.count("<body") == 1
    assert re.findall(r'data-page-id="(\d+)"', html) == ["0", "1"]
    assert "vicomte" in html


@pytest.mark.parametrize("backend", BACKENDS)
def test_rejected_api_key_exits_with_usage_error(tmp_path, backend):
    sample = SAMPLES[1]
    source = tmp_path / sample.filename
    shutil.copy(sample.path, source)
    console = CapturingConsole()
    args = [str(source), "--backend", backend, "--api-key", "definitely-not-a-valid-key"]
    assert cli.main(args, console=console) == cli.EXIT_USAGE
    assert "Authentication failed" in console.err
