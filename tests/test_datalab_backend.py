"""DatalabBackend: request fields, submit/poll, resubmits, and timeouts.

These run through the real pipeline with ``FakeClient`` standing in for the
HTTP client, which is tested on its own in ``test_datalab_client.py``.
"""

from __future__ import annotations

import threading
import time

import pytest

import docs_to_md.backends.datalab.backend as backend_module
from docs_to_md.backends import BACKENDS, DEFAULT_BACKEND, get_backend
from docs_to_md.backends.datalab import DatalabBackend
from docs_to_md.backends.datalab.client import DatalabClient
from docs_to_md.backends.datalab.models import INPUT_MIME_TYPES, ConvertResult
from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import ConfigurationError, RetryableAPIError
from docs_to_md.pdf import Chunk
from docs_to_md.pipeline import Pipeline

from .conftest import FakeClient


def run(inputs, console, client=None, **overrides):
    config = Config(inputs=list(inputs), api_key="k", **overrides).validate()
    client = client or FakeClient()
    jobs = plan_jobs(
        config.inputs,
        config.output_format,
        config.output_dir,
        input_extensions=DatalabBackend.info.input_extensions,
    )
    return Pipeline(config, console, backend=DatalabBackend(config, client)).run(jobs)


def test_is_the_default_backend():
    assert DEFAULT_BACKEND == "datalab"
    assert BACKENDS["datalab"] is DatalabBackend
    assert get_backend("datalab") is DatalabBackend


def test_unknown_backend_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="Unknown backend: nope"):
        get_backend("nope")


def test_info_describes_the_convert_api():
    info = DatalabBackend.info
    assert info.input_extensions == set(INPUT_MIME_TYPES)
    assert {"pdf", "docx", "csv", "xlsm", "epub", "png"} <= info.input_extensions
    assert info.output_formats == {"markdown", "html", "json"}
    assert info.modes == ("fast", "balanced", "accurate")
    assert info.max_upload_bytes == 200 * 1024 * 1024
    assert info.api_key_env_vars == ("DATALAB_API_KEY", "MARKER_PDF_KEY")
    assert info.requires_api_key


def test_from_config_builds_an_authenticated_client(tmp_path):
    stop = threading.Event()
    config = Config(inputs=[tmp_path], api_key="secret").validate()
    backend = DatalabBackend.from_config(config, stop)
    assert isinstance(backend.client, DatalabClient)
    assert backend.client.headers == {"X-API-Key": "secret"}
    assert backend.client.stop_event is stop


def test_options_forward_the_config(tmp_path):
    config = Config(
        inputs=[tmp_path],
        api_key="k",
        output_format="html",
        mode="accurate",
        paginate=True,
        disable_image_extraction=True,
        disable_image_captions=True,
        skip_cache=True,
        extra_options={"extras": "extract_links"},
    ).validate()
    form = DatalabBackend(config, FakeClient()).options_for(Chunk(tmp_path / "a.pdf", (0,))).to_form()
    assert form == {
        "output_format": "html",
        "mode": "accurate",
        "paginate": "true",
        "disable_image_extraction": "true",
        "disable_image_captions": "true",
        "skip_cache": "true",
        "extras": "extract_links",
    }


def test_split_pdfs_do_not_send_page_selection(examples, console):
    client = FakeClient()
    run([examples / "alice_in_wonderland_sample.pdf"], console, client, chunk_size=1, max_pages=2)
    assert len(client.submissions) == 2
    for _, options in client.submissions:
        form = options.to_form()
        assert "max_pages" not in form and "page_range" not in form


def test_whole_documents_send_page_selection(tmp_path, console):
    doc = tmp_path / "slides.pptx"
    doc.write_bytes(b"pptx")
    client = FakeClient()
    run([doc], console, client, page_range="0-1", mode="accurate")
    [(path, options)] = client.submissions
    assert path == doc
    assert options.to_form()["page_range"] == "0-1"
    assert options.to_form()["mode"] == "accurate"


def test_result_page_count_and_cost_are_reported(examples, console):
    summary = run([examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=2)
    assert summary.exit_code == 0
    assert summary.pages == 2  # FakeClient reports page_count=1 per request
    assert summary.cost_cents == pytest.approx(0.6)


def test_complete_without_success_is_a_failure(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="complete", success=False, error="bad pdf")])
    summary = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 1
    assert "bad pdf" in console.err


def test_failed_status_reports_the_api_error(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="failed", error="Could not parse")])
    summary = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 1
    assert "equations.pdf: Could not parse" in console.err


def test_missing_output_format_content_is_a_failure(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="complete", success=True, markdown="# x")])
    summary = run([examples / "equations.pdf"], console, client, output_format="html")
    assert summary.exit_code == 1
    assert "no html output" in console.err


def test_page_rate_limit_results_are_resubmitted(examples, console):
    def responder(path, options, index):
        if index == 0:
            return [ConvertResult(status="complete", success=False, error="Page rate limit exceeded")]
        return FakeClient.default_responder(path, options, index)

    client = FakeClient(responder)
    summary = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 0
    assert len(client.submissions) == 2


def test_rate_limit_gives_up_after_the_resubmit_budget(examples, console):
    client = FakeClient(lambda *a: [ConvertResult(status="failed", error="Page rate limit exceeded")])
    summary = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 1
    assert len(client.submissions) == backend_module.MAX_RATE_LIMIT_RESUBMITS + 1


def test_transient_poll_errors_are_tolerated(examples, console):
    client = FakeClient()
    real_get = client.get_result
    calls = {"n": 0}

    def flaky(request_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableAPIError("HTTP 503")
        return real_get(request_id)

    client.get_result = flaky
    summary = run([examples / "equations.pdf"], console, client)
    assert summary.exit_code == 0


def test_timeout_fails_the_file(examples, console, monkeypatch):
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(backend_module.time, "monotonic", lambda: next(clock))
    client = FakeClient(lambda *a: [ConvertResult(status="processing")])
    summary = run([examples / "equations.pdf"], console, client, timeout=250)
    assert summary.exit_code == 1
    assert "timed out after 4m10s" in console.err


def test_polling_stops_when_a_sibling_chunk_fails(examples, console):
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

    summary = run(
        [examples / "alice_in_wonderland_sample.pdf"], console, Client(), chunk_size=1, concurrency=3
    )
    assert summary.exit_code == 1
    # Without the abort the slow chunk would be polled until the 1-hour timeout.
    assert polls["slow"] < 1000
