"""Offline checks over every sample document in ``examples/``."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import unquote

import pytest

from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.pdf import count_pages, split_pdf
from docs_to_md.pipeline import Pipeline

from .conftest import FakeClient
from .samples import EXAMPLES, SAMPLES

IDS = [s.filename for s in SAMPLES]


def test_manifest_lists_every_sample_pdf():
    assert sorted(p.name for p in EXAMPLES.glob("*.pdf")) == sorted(IDS)


@pytest.mark.parametrize("sample", SAMPLES, ids=IDS)
def test_sample_page_count(sample):
    assert count_pages(sample.path) == sample.pages


@pytest.mark.parametrize("sample", [s for s in SAMPLES if s.pages > 1], ids=lambda s: s.filename)
def test_sample_splits_into_single_pages(sample, tmp_path):
    chunks = split_pdf(sample.path, tmp_path, chunk_size=1)
    assert [list(c.pages) for c in chunks] == [[p] for p in range(sample.pages)]
    assert all(count_pages(c.path) == 1 for c in chunks)


@pytest.mark.parametrize("sample", SAMPLES, ids=IDS)
def test_reference_output_is_complete(sample):
    """The committed ``<stem>.md`` next to each sample is a valid conversion."""
    output = sample.path.with_suffix(".md")
    text = output.read_text(encoding="utf-8")
    for keyword in sample.keywords:
        assert keyword.casefold() in text.casefold(), f"{keyword!r} missing from {output.name}"
    assert sum(line.startswith("|") for line in text.splitlines()) >= sample.min_table_rows
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert bool(links) == sample.has_images
    for link in links:
        assert (EXAMPLES / unquote(link)).is_file(), f"broken image link {link}"


def test_every_sample_converts_through_the_pipeline(tmp_path, console):
    source = tmp_path / "samples"
    source.mkdir()
    for sample in SAMPLES:
        shutil.copy(sample.path, source / sample.filename)
    client = FakeClient()
    config = Config(inputs=[source], api_key="k", chunk_size=1).validate()
    summary = Pipeline(config, console, client=client).run(plan_jobs(config.inputs, "markdown"))
    assert summary.exit_code == 0
    assert len(client.submissions) == sum(s.pages for s in SAMPLES)
    assert sorted(p.name for p in Path(source).glob("*.md")) == sorted(
        s.filename.replace(".pdf", ".md") for s in SAMPLES
    )
