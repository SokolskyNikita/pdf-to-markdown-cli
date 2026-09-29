from __future__ import annotations

import pytest
import requests

from docs_to_md.backends.datalab.client import MAX_ATTEMPTS, DatalabClient
from docs_to_md.backends.datalab.models import ConvertOptions
from docs_to_md.errors import APIError, Cancelled, FatalAPIError, RetryableAPIError

from .conftest import FakeResponse, FakeSession


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    return path


def make_client(*responses):
    client = DatalabClient("secret", base_url="https://api.test/v1")
    session = FakeSession(*responses)
    client._local.session = session
    client.delays = []
    client.sleep = client.delays.append
    return client, session


def test_submit_posts_file_and_options(pdf):
    client, session = make_client(FakeResponse(payload={"success": True, "request_id": "abc"}))
    assert client.submit(pdf, ConvertOptions(mode="balanced")) == "abc"
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://api.test/v1/convert")
    assert kwargs["data"] == {"output_format": "markdown", "mode": "balanced"}
    assert kwargs["files"]["file"][0] == "doc.pdf"
    assert kwargs["files"]["file"][2] == "application/pdf"
    assert kwargs["file_bytes"] == b"%PDF-1.4 test"


def test_session_sends_api_key_header():
    client = DatalabClient("  secret  ")
    assert client._session.headers["X-API-Key"] == "secret"


def test_retries_rate_limit_honoring_retry_after(pdf):
    client, session = make_client(
        FakeResponse(429, {"detail": "slow down"}, headers={"Retry-After": "7"}),
        FakeResponse(503, text="unavailable"),
        FakeResponse(payload={"success": True, "request_id": "abc"}),
    )
    assert client.submit(pdf, ConvertOptions()) == "abc"
    assert len(session.calls) == 3
    assert client.delays[0] == 7
    assert 0 < client.delays[1] <= 60


def test_retries_dropped_downloads():
    client, _ = make_client(
        requests.exceptions.ChunkedEncodingError("connection broken"),
        FakeResponse(payload={"status": "processing"}),
    )
    assert client.get_result("abc").status == "processing"


def test_retries_network_errors_then_gives_up(pdf):
    errors = [requests.ConnectionError("boom") for _ in range(MAX_ATTEMPTS)]
    client, session = make_client(*errors)
    with pytest.raises(RetryableAPIError, match="network error"):
        client.submit(pdf, ConvertOptions())
    assert len(session.calls) == MAX_ATTEMPTS
    assert len(client.delays) == MAX_ATTEMPTS - 1


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_fatal_and_not_retried(pdf, status):
    client, session = make_client(FakeResponse(status, {"detail": "bad key"}))
    with pytest.raises(FatalAPIError, match="Authentication failed"):
        client.submit(pdf, ConvertOptions())
    assert len(session.calls) == 1


def test_payment_required_is_fatal(pdf):
    client, _ = make_client(FakeResponse(402, {"detail": "Out of credits"}))
    with pytest.raises(FatalAPIError, match="Out of credits"):
        client.submit(pdf, ConvertOptions())


def test_file_too_large(pdf):
    client, _ = make_client(FakeResponse(413))
    with pytest.raises(APIError, match="200 MB"):
        client.submit(pdf, ConvertOptions())


def test_client_error_reports_detail(pdf):
    client, _ = make_client(FakeResponse(422, {"detail": "bad page_range"}))
    with pytest.raises(APIError, match="bad page_range"):
        client.submit(pdf, ConvertOptions())


def test_rejected_submission(pdf):
    client, _ = make_client(FakeResponse(payload={"success": False, "error": "nope", "request_id": None}))
    with pytest.raises(APIError, match="nope"):
        client.submit(pdf, ConvertOptions())


def test_invalid_json_is_retried(pdf):
    client, _ = make_client(
        FakeResponse(200, None, text="<html>"),
        FakeResponse(payload={"success": True, "request_id": "abc"}),
    )
    assert client.submit(pdf, ConvertOptions()) == "abc"


def test_unsupported_extension_is_rejected_locally(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    client, session = make_client()
    with pytest.raises(APIError, match="Unsupported file type"):
        client.submit(path, ConvertOptions())
    assert session.calls == []


def test_get_result_parses_payload():
    client, session = make_client(
        FakeResponse(payload={"status": "complete", "success": True, "markdown": "# hi", "page_count": 1})
    )
    result = client.get_result("abc")
    assert session.calls[0][1] == "https://api.test/v1/convert/abc"
    assert (result.status, result.markdown, result.page_count) == ("complete", "# hi", 1)


def test_get_result_not_found_means_expired():
    client, _ = make_client(FakeResponse(404))
    with pytest.raises(APIError, match="expired"):
        client.get_result("abc")


def test_get_result_downloads_from_result_url(monkeypatch):
    client, _ = make_client(
        FakeResponse(payload={"status": "complete", "success": True, "result_url": "https://dl/x"})
    )
    fetched = []

    def fake_get(url, **kwargs):
        fetched.append(url)
        return FakeResponse(payload={"markdown": "# big", "page_count": 900})

    monkeypatch.setattr(requests, "get", fake_get)
    result = client.get_result("abc")
    assert fetched == ["https://dl/x"]
    assert (result.status, result.markdown, result.page_count) == ("complete", "# big", 900)


def test_rejected_download_link_is_not_an_auth_failure(monkeypatch):
    client, _ = make_client(
        FakeResponse(payload={"status": "complete", "success": True, "result_url": "https://dl/x"})
    )
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: FakeResponse(403))
    with pytest.raises(APIError, match="download link") as exc:
        client.get_result("abc")
    assert not isinstance(exc.value, FatalAPIError)


def test_cancelled_client_stops_before_calling(pdf):
    client, session = make_client()
    client.stop_event.set()
    with pytest.raises(Cancelled):
        client.submit(pdf, ConvertOptions())
    assert session.calls == []


def test_real_sleep_wakes_on_cancel():
    client = DatalabClient("secret")
    client.stop_event.set()
    with pytest.raises(Cancelled):
        client.sleep(30)


def test_empty_api_key_rejected():
    with pytest.raises(FatalAPIError):
        DatalabClient("   ")
