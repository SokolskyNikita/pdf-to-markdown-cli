from __future__ import annotations

import threading
import time

import pytest

import docs_to_md.pipeline as pipeline_module
from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import APIError, FatalAPIError
from docs_to_md.models import ConvertResult
from docs_to_md.pipeline import FAILED, SKIPPED, Pipeline, format_cost, format_elapsed

from .conftest import FakeClient


def run(inputs, console, client=None, **overrides):
    config = Config(inputs=list(inputs), api_key="k", **overrides).validate()
    jobs = plan_jobs(config.inputs, config.output_format, config.output_dir)
    pipeline = Pipeline(config, console, client=client or FakeClient())
    return pipeline.run(jobs), pipeline


def test_converts_and_merges_chunks(examples, console):
    client = FakeClient()
    summary, _ = run([examples / "alice_in_wonderland_sample.pdf"], console, client, chunk_size=2)
    assert summary.exit_code == 0
    assert len(client.submissions) == 2  # 3 pages / 2 per chunk
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
    assert "✓" in console.err and "2 pages" in console.err and "$0.0060" in console.err
    assert summary.pages == 2 and summary.cost_cents == pytest.approx(0.6)


def test_small_pdf_uploads_original_file(examples, console):
    client = FakeClient()
    run([examples / "equations.pdf"], console, client)
    [(path, options)] = client.submissions
    assert path == examples / "equations.pdf"
    assert "max_pages" not in options.to_form()


def test_pdf_page_selection_is_local(examples, console):
    client = FakeClient()
    run([examples / "alice_in_wonderland_sample.pdf"], console, client, chunk_size=1, max_pages=2)
    assert len(client.submissions) == 2
    for _, options in client.submissions:
        form = options.to_form()
        assert "max_pages" not in form and "page_range" not in form


def test_non_pdf_page_selection_is_sent_to_api(tmp_path, console):
    doc = tmp_path / "slides.pptx"
    doc.write_bytes(b"pptx")
    client = FakeClient()
    run([doc], console, client, page_range="0-1", mode="accurate")
    [(path, options)] = client.submissions
    assert path == doc
    assert options.to_form()["page_range"] == "0-1"
    assert options.to_form()["mode"] == "accurate"


@pytest.mark.parametrize("fmt", ["html", "json"])
def test_other_formats_are_written(examples, console, fmt):
    summary, _ = run([examples / "equations.pdf"], console, output_format=fmt)
    assert summary.exit_code == 0
    assert (examples / f"equations.{fmt}").exists()


def test_existing_output_is_skipped_unless_overwrite(examples, console):
    target = examples / "equations.md"
    target.write_text("keep me")
    client = FakeClient()
    summary, _ = run([examples / "equations.pdf"], console, client)
    assert summary.count(SKIPPED) == 1 and summary.exit_code == 0
    assert client.submissions == [] and target.read_text() == "keep me"
    assert "use --overwrite" in console.err

    summary, _ = run([examples / "equations.pdf"], console, client, overwrite=True)
    assert summary.count(SKIPPED) == 0
    assert target.read_text().startswith("# equations.pdf")


def test_existing_images_dir_also_blocks_conversion(examples, console):
    (examples / "equations_images").mkdir()
    summary, _ = run([examples / "equations.pdf"], console)
    assert summary.count(SKIPPED) == 1


def test_failed_file_does_not_stop_others(examples, console):
    def responder(path, options, index):
        if path.name == "equations.pdf":
            return [ConvertResult(status="failed", success=False, error="Could not parse")]
        return FakeClient.default_responder(path, options, index)

    summary, _ = run([examples], console, FakeClient(responder))
    assert summary.exit_code == 1
    assert summary.count(FAILED) == 1
    assert (examples / "alice_in_wonderland_sample.md").exists()
    assert not (examples / "equations.md").exists()
    assert "equations.pdf: Could not parse" in console.err


def test_complete_without_success_is_a_failure(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="complete", success=False, error="bad pdf")])
    summary, _ = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 1


def test_missing_output_format_content_is_a_failure(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="complete", success=True, markdown="# x")])
    summary, _ = run([examples / "equations.pdf"], console, client, output_format="html")
    assert summary.exit_code == 1
    assert "no html output" in console.err


def test_one_failed_chunk_fails_the_file_without_partial_output(examples, console):
    def responder(path, options, index):
        if path.name == "0002of0003.pdf":
            return [ConvertResult(status="failed", error="boom")]
        return FakeClient.default_responder(path, options, index)

    summary, _ = run(
        [examples / "alice_in_wonderland_sample.pdf"], console, FakeClient(responder), chunk_size=1
    )
    assert summary.exit_code == 1
    assert not (examples / "alice_in_wonderland_sample.md").exists()


def test_failed_chunk_stops_its_siblings_early(examples, console):
    polls = {"slow": 0}

    class Client(FakeClient):
        def get_result(self, request_id):
            if request_id == "req-0":  # first chunk never finishes on its own
                polls["slow"] += 1
                return ConvertResult(status="processing")
            return ConvertResult(status="failed", error="boom")

        def sleep(self, seconds):
            super().sleep(seconds)
            time.sleep(0.001)

    config = Config(
        inputs=[examples / "alice_in_wonderland_sample.pdf"], api_key="k", chunk_size=1, concurrency=3
    )
    summary = Pipeline(config, console, client=Client()).run(plan_jobs(config.inputs, "markdown"))
    assert summary.exit_code == 1
    # Without the abort the slow chunk would be polled until the 1-hour timeout.
    assert polls["slow"] < 1000


def test_fatal_error_in_a_later_file_is_reported_as_fatal(examples, console):
    class Client(FakeClient):
        def submit(self, path, options):
            if path.name == "equations.pdf":
                raise FatalAPIError("Payment required: out of credits.")
            return super().submit(path, options)

        def get_result(self, request_id):
            return ConvertResult(status="processing")

        def sleep(self, seconds):
            super().sleep(seconds)
            time.sleep(0.001)

    config = Config(inputs=[examples], api_key="k").validate()
    with pytest.raises(FatalAPIError, match="out of credits"):
        Pipeline(config, console, client=Client()).run(plan_jobs(config.inputs, "markdown"))


def test_page_rate_limit_results_are_resubmitted(examples, console):
    def responder(path, options, index):
        if index == 0:
            return [ConvertResult(status="complete", success=False, error="Page rate limit exceeded")]
        return FakeClient.default_responder(path, options, index)

    client = FakeClient(responder)
    summary, _ = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 0
    assert len(client.submissions) == 2


def test_transient_poll_errors_are_tolerated(examples, console):
    client = FakeClient()
    real_get = client.get_result
    calls = {"n": 0}

    def flaky(request_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pipeline_module.RetryableAPIError("HTTP 503")
        return real_get(request_id)

    client.get_result = flaky
    summary, _ = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 0


def test_timeout_fails_the_file(examples, console, monkeypatch):
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(pipeline_module.time, "monotonic", lambda: next(clock))
    client = FakeClient(lambda *a: [ConvertResult(status="processing")])
    summary, _ = run([examples / "equations.pdf"], console, client, timeout=250)
    assert summary.exit_code == 1
    assert "timed out" in console.err


def test_fatal_error_aborts_the_run(examples, console):
    class AuthFailClient(FakeClient):
        def submit(self, path, options):
            raise FatalAPIError("Authentication failed")

    with pytest.raises(FatalAPIError):
        run([examples], console, AuthFailClient())


def test_unreadable_pdf_is_reported_and_others_continue(examples, console):
    (examples / "broken.pdf").write_bytes(b"garbage")
    summary, _ = run([examples], console)
    assert summary.count(FAILED) == 1
    assert "broken.pdf" in console.err
    assert (examples / "equations.md").exists()


def test_oversized_non_pdf_is_rejected_before_upload(tmp_path, console, monkeypatch):
    monkeypatch.setattr(pipeline_module, "MAX_UPLOAD_BYTES", 3)
    doc = tmp_path / "big.docx"
    doc.write_bytes(b"12345")
    client = FakeClient()
    summary, _ = run([doc], console, client)
    assert summary.exit_code == 1 and client.submissions == []
    assert "200 MB" in console.err


def test_dry_run_makes_no_api_calls(examples, console):
    config = Config(inputs=[examples], dry_run=True, chunk_size=2).validate()
    jobs = plan_jobs(config.inputs, config.output_format)
    summary = Pipeline(config, console, client=None).run(jobs)
    assert summary.exit_code == 0
    assert "alice_in_wonderland_sample.pdf → " in console.err
    assert "(3 pages, 2 chunks)" in console.err
    assert "(1 page, 1 chunk)" in console.err
    assert not list(examples.glob("*.md"))


def test_dry_run_reports_unreadable_pdf(tmp_path, console):
    (tmp_path / "broken.pdf").write_bytes(b"garbage")
    config = Config(inputs=[tmp_path], dry_run=True).validate()
    summary = Pipeline(config, console).run(plan_jobs(config.inputs, "markdown"))
    assert summary.exit_code == 1


def test_stop_event_cancels_workers(examples, console):
    stop = threading.Event()
    client = FakeClient(lambda *a: [ConvertResult(status="processing")])
    client.stop_event = stop
    config = Config(inputs=[examples / "equations.pdf"], api_key="k").validate()
    pipeline = Pipeline(config, console, client=client, stop_event=stop)
    original_sleep = client.sleep

    def sleep_then_stop(seconds):
        stop.set()
        original_sleep(seconds)

    client.sleep = sleep_then_stop
    with pytest.raises(pipeline_module.Cancelled):
        pipeline.run(plan_jobs(config.inputs, "markdown"))


def test_missing_client_is_fatal(examples, console):
    config = Config(inputs=[examples / "equations.pdf"], api_key="k").validate()
    with pytest.raises(FatalAPIError):
        Pipeline(config, console).run(plan_jobs(config.inputs, "markdown"))


@pytest.mark.parametrize(("cents", "text"), [(0, "$0.00"), (0.3, "$0.0030"), (1, "$0.01"), (1234, "$12.34")])
def test_format_cost(cents, text):
    assert format_cost(cents) == text


@pytest.mark.parametrize(("seconds", "text"), [(4.25, "4.2s"), (65, "1m05s"), (3600, "60m00s")])
def test_format_elapsed(seconds, text):
    assert format_elapsed(seconds) == text


def test_api_error_class_is_reexported():
    assert issubclass(pipeline_module.RetryableAPIError, APIError)
