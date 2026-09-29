"""Pipeline orchestration, tested against an in-memory backend.

Datalab-specific behavior (polling, resubmits, request fields) is covered in
``test_datalab_backend.py``.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import pytest

import docs_to_md.pipeline as pipeline_module
from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import APIError, Cancelled, FatalAPIError
from docs_to_md.pipeline import FAILED, SKIPPED, Pipeline

from .conftest import FakeBackend


def run(inputs, console, backend=None, **overrides):
    config = Config(inputs=list(inputs), api_key="k", **overrides).validate()
    backend = backend or FakeBackend(config.output_format)
    jobs = plan_jobs(
        config.inputs, config.output_format, config.output_dir, input_extensions=backend.info.input_extensions
    )
    return Pipeline(config, console, backend=backend).run(jobs)


def block_until_cancelled(chunk, check_cancelled):
    while True:
        check_cancelled()
        time.sleep(0.001)


def test_converts_and_merges_chunks(examples, console):
    backend = FakeBackend()
    summary = run([examples / "alice_in_wonderland_sample.pdf"], console, backend, chunk_size=2)
    assert summary.exit_code == 0
    assert sorted(tuple(c.pages) for c in backend.chunks) == [(0, 1), (2,)]
    output = examples / "alice_in_wonderland_sample.md"
    text = output.read_text()
    assert text.count("# 0001of0002.pdf") == 1
    assert text.count("# 0002of0002.pdf") == 1
    assert text.index("0001of0002") < text.index("0002of0002")
    assert sorted(p.name for p in (examples / "alice_in_wonderland_sample_images").iterdir()) == [
        "chunk2_img.png",
        "img.png",
    ]
    assert console.out == f"{output}\n"
    assert "✓" in console.err and "3 pages" in console.err and "$0.0060" in console.err
    assert summary.pages == 3 and summary.cost_cents == pytest.approx(0.6)


def test_small_pdf_is_sent_as_the_original_file(examples, console):
    backend = FakeBackend()
    run([examples / "equations.pdf"], console, backend)
    [chunk] = backend.chunks
    assert chunk.path == examples / "equations.pdf"
    assert list(chunk.pages) == [0]


def test_pdf_page_selection_happens_before_the_backend(examples, console):
    backend = FakeBackend()
    run([examples / "alice_in_wonderland_sample.pdf"], console, backend, chunk_size=1, page_range="1-2")
    assert sorted(tuple(c.pages) for c in backend.chunks) == [(1,), (2,)]


def test_non_pdf_is_sent_whole_without_pages(tmp_path, console):
    doc = tmp_path / "slides.pptx"
    doc.write_bytes(b"pptx")
    backend = FakeBackend()
    run([doc], console, backend, page_range="0-1")
    [chunk] = backend.chunks
    assert chunk.path == doc and not chunk.pages


def test_only_extensions_the_backend_accepts_are_discovered(tmp_path, console):
    (tmp_path / "book.epub").write_bytes(b"epub")  # Datalab reads EPUB; the fake backend does not
    (tmp_path / "notes.docx").write_bytes(b"docx")
    backend = FakeBackend()
    run([tmp_path], console, backend)
    assert [c.path.name for c in backend.chunks] == ["notes.docx"]


@pytest.mark.parametrize("fmt", ["html", "json"])
def test_other_formats_are_written(examples, console, fmt):
    summary = run([examples / "equations.pdf"], console, output_format=fmt)
    assert summary.exit_code == 0
    assert (examples / f"equations.{fmt}").exists()


def test_existing_output_is_skipped_unless_overwrite(examples, console):
    target = examples / "equations.md"
    target.write_text("keep me")
    backend = FakeBackend()
    summary = run([examples / "equations.pdf"], console, backend)
    assert summary.count(SKIPPED) == 1 and summary.exit_code == 0
    assert backend.chunks == [] and target.read_text() == "keep me"
    assert "use --overwrite" in console.err

    summary = run([examples / "equations.pdf"], console, backend, overwrite=True)
    assert summary.count(SKIPPED) == 0
    assert target.read_text().startswith("# equations.pdf")


def test_existing_images_dir_also_blocks_conversion(examples, console):
    (examples / "equations_images").mkdir()
    summary = run([examples / "equations.pdf"], console)
    assert summary.count(SKIPPED) == 1


def test_failed_file_does_not_stop_others(examples, console):
    def handler(chunk, check_cancelled):
        if chunk.path.name == "equations.pdf":
            raise APIError("Could not parse")
        return backend.default_handler(chunk, check_cancelled)

    backend = FakeBackend(handler=handler)
    summary = run([examples], console, backend)
    assert summary.exit_code == 1
    assert summary.count(FAILED) == 1
    assert (examples / "alice_in_wonderland_sample.md").exists()
    assert not (examples / "equations.md").exists()
    assert "equations.pdf: Could not parse" in console.err


def test_one_failed_chunk_fails_the_file_without_partial_output(examples, console):
    def handler(chunk, check_cancelled):
        if chunk.path.name == "0002of0003.pdf":
            raise APIError("boom")
        return backend.default_handler(chunk, check_cancelled)

    backend = FakeBackend(handler=handler)
    summary = run([examples / "alice_in_wonderland_sample.pdf"], console, backend, chunk_size=1)
    assert summary.exit_code == 1
    assert not (examples / "alice_in_wonderland_sample.md").exists()


def test_failed_chunk_cancels_its_siblings(examples, console):
    def handler(chunk, check_cancelled):
        if chunk.path.name == "0001of0003.pdf":
            block_until_cancelled(chunk, check_cancelled)
        raise APIError("boom")

    summary = run(
        [examples / "alice_in_wonderland_sample.pdf"],
        console,
        FakeBackend(handler=handler),
        chunk_size=1,
        concurrency=3,
    )
    # Without the abort the first chunk would block forever.
    assert summary.exit_code == 1


def test_unexpected_backend_exception_fails_only_that_file(examples, console):
    def handler(chunk, check_cancelled):
        if chunk.path.name == "equations.pdf":
            raise RuntimeError("bug in backend")
        return backend.default_handler(chunk, check_cancelled)

    backend = FakeBackend(handler=handler)
    summary = run([examples], console, backend)
    assert summary.count(FAILED) == 1
    assert "equations.pdf: bug in backend" in console.err


def test_fatal_error_aborts_the_run(examples, console):
    def handler(chunk, check_cancelled):
        raise FatalAPIError("Authentication failed")

    with pytest.raises(FatalAPIError):
        run([examples], console, FakeBackend(handler=handler))


def test_fatal_error_in_a_later_file_is_reported_as_fatal(examples, console):
    def handler(chunk, check_cancelled):
        if chunk.path.name == "equations.pdf":
            raise FatalAPIError("Payment required: out of credits.")
        block_until_cancelled(chunk, check_cancelled)

    with pytest.raises(FatalAPIError, match="out of credits"):
        run([examples], console, FakeBackend(handler=handler))


def test_unreadable_pdf_is_reported_and_others_continue(examples, console):
    (examples / "broken.pdf").write_bytes(b"garbage")
    summary = run([examples], console)
    assert summary.count(FAILED) == 1
    assert "broken.pdf" in console.err
    assert (examples / "equations.md").exists()


def test_oversized_whole_document_is_rejected_before_conversion(tmp_path, console):
    class SmallLimit(FakeBackend):
        info = dataclasses.replace(FakeBackend.info, max_upload_bytes=3)

    doc = tmp_path / "big.docx"
    doc.write_bytes(b"12345")
    backend = SmallLimit()
    summary = run([doc], console, backend)
    assert summary.exit_code == 1 and backend.chunks == []
    assert "larger than Fake's 3 bytes upload limit" in console.err


def test_dry_run_needs_no_backend(examples, console):
    config = Config(inputs=[examples], dry_run=True, chunk_size=2).validate()
    jobs = plan_jobs(config.inputs, config.output_format, input_extensions={"pdf"})
    summary = Pipeline(config, console).run(jobs)
    assert summary.exit_code == 0
    assert "alice_in_wonderland_sample.pdf → " in console.err
    assert "(3 pages, 2 chunks)" in console.err
    assert "(1 page, 1 chunk)" in console.err
    assert not list(examples.glob("*.md"))


def test_dry_run_reports_unreadable_pdf(tmp_path, console):
    (tmp_path / "broken.pdf").write_bytes(b"garbage")
    config = Config(inputs=[tmp_path], dry_run=True).validate()
    summary = Pipeline(config, console).run(plan_jobs(config.inputs, "markdown", input_extensions={"pdf"}))
    assert summary.exit_code == 1


def test_stop_event_cancels_workers(examples, console):
    stop = threading.Event()

    def handler(chunk, check_cancelled):
        stop.set()
        block_until_cancelled(chunk, check_cancelled)

    config = Config(inputs=[examples / "equations.pdf"], api_key="k").validate()
    pipeline = Pipeline(config, console, backend=FakeBackend(handler=handler), stop_event=stop)
    with pytest.raises(Cancelled):
        pipeline.run(plan_jobs(config.inputs, "markdown", input_extensions={"pdf"}))


def test_missing_backend_is_fatal(examples, console):
    config = Config(inputs=[examples / "equations.pdf"], api_key="k").validate()
    with pytest.raises(FatalAPIError, match="No conversion backend"):
        Pipeline(config, console).run(plan_jobs(config.inputs, "markdown", input_extensions={"pdf"}))


@pytest.mark.parametrize(
    ("size", "text"), [(3, "3 bytes"), (200 * 1024 * 1024, "200 MB"), (1536 * 1024, "1.5 MB")]
)
def test_format_size(size, text):
    assert pipeline_module._format_size(size) == text
