from __future__ import annotations

import pytest

from docs_to_md.backends.mistral.client import MistralClient
from docs_to_md.errors import APIError, FatalAPIError, RetryableAPIError

from .conftest import FakeResponse, FakeSession

BODY = {"model": "mistral-ocr-4-0", "document": {}}


def make_client(*responses):
    client = MistralClient("secret", base_url="https://api.test/v1", timeout=90)
    session = FakeSession(*responses)
    client._local.session = session
    client.delays = []
    client.sleep = client.delays.append
    return client, session


def error(status, message="nope", kind="invalid_request_error", headers=None):
    body = {"object": "error", "message": message, "type": kind, "param": None, "code": "1"}
    return FakeResponse(status, body, headers=headers)


def test_posts_the_body_to_ocr():
    client, session = make_client(FakeResponse(payload={"pages": []}))
    assert client.ocr(BODY, "OCR of a.pdf") == {"pages": []}
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://api.test/v1/ocr")
    assert kwargs["json"] == BODY
    assert kwargs["timeout"] == (15, 90)


def test_session_sends_bearer_token():
    client = MistralClient("  secret  ")
    assert client._session.headers["Authorization"] == "Bearer secret"
    assert (client.base_url, client.label) == ("https://api.mistral.ai/v1", "Mistral")


def test_auth_failure_is_fatal():
    # Mistral's real 401 body.
    client, session = make_client(FakeResponse(401, {"detail": "Invalid API Key"}))
    with pytest.raises(FatalAPIError, match=r"Mistral rejected your API key \(HTTP 401: Invalid API Key\)"):
        client.ocr(BODY, "t")
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (error(400, "Invalid model: mistral-ocr-9", "invalid_model"), "refused the request"),
        (error(403, "forbidden"), "refused the request"),
        (FakeResponse(402, text="Payment Required"), "out of credits"),
    ],
)
def test_account_and_model_errors_are_fatal(response, message):
    client, session = make_client(response)
    with pytest.raises(FatalAPIError, match=message):
        client.ocr(BODY, "t")
    assert len(session.calls) == 1


def test_retries_rate_limits_honoring_retry_after():
    client, session = make_client(
        error(429, "Requests rate limit exceeded", "rate_limit_error", headers={"Retry-After": "4"}),
        error(503, "busy", "server_error"),
        FakeResponse(payload={"pages": []}),
    )
    assert client.ocr(BODY, "t") == {"pages": []}
    assert len(session.calls) == 3
    assert client.delays[0] == 4.0


def test_retries_give_up_eventually():
    client, _ = make_client(*[error(500, "boom", "server_error")] * 6)
    with pytest.raises(RetryableAPIError, match="t: HTTP 500: boom"):
        client.ocr(BODY, "t")


def test_file_errors_report_detail():
    client, _ = make_client(error(400, "Document type 'application/octet-stream' is not supported"))
    with pytest.raises(APIError, match="t: HTTP 400: Document type") as info:
        client.ocr(BODY, "t")
    assert not isinstance(info.value, FatalAPIError)
    client, _ = make_client(FakeResponse(413, text="too big"))
    with pytest.raises(APIError, match="limit is 50 MB"):
        client.ocr(BODY, "t")


def test_validation_errors_are_flattened():
    # Mistral's real 422 body for --api-option table_format=latex.
    detail = [{"type": "literal_error", "loc": ["body", "table_format"], "msg": "Input should be 'markdown'"}]
    body = {"object": "error", "message": {"detail": detail}, "type": "invalid_request_error"}
    client, _ = make_client(FakeResponse(422, body))
    with pytest.raises(APIError, match="HTTP 422: table_format: Input should be 'markdown'"):
        client.ocr(BODY, "t")
    client, _ = make_client(FakeResponse(422, {"detail": ["plain"]}))
    with pytest.raises(APIError, match=r"HTTP 422: plain$"):
        client.ocr(BODY, "t")
    client, _ = make_client(FakeResponse(418, ["odd"]))
    with pytest.raises(APIError, match=r"HTTP 418: \['odd'\]"):
        client.ocr(BODY, "t")
    client, _ = make_client(FakeResponse(418, text=""))
    with pytest.raises(APIError, match="HTTP 418: reason"):
        client.ocr(BODY, "t")


def test_empty_api_key_rejected():
    with pytest.raises(FatalAPIError):
        MistralClient("  ")
