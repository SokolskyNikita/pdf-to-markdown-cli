from __future__ import annotations

import pytest
import requests

from docs_to_md.backends.openai.client import MAX_ATTEMPTS, OpenAIClient
from docs_to_md.errors import APIError, Cancelled, FatalAPIError, RetryableAPIError

from .conftest import FakeResponse, FakeSession

BODY = {"model": "gpt-6-luna", "input": []}


def make_client(*responses, label="OpenAI"):
    client = OpenAIClient("secret", base_url="https://api.test/v1", timeout=90, label=label)
    session = FakeSession(*responses)
    client._local.session = session
    client.delays = []
    client.sleep = client.delays.append
    return client, session


def error(status, message="nope", code=None, headers=None):
    return FakeResponse(status, {"error": {"message": message, "code": code}}, headers=headers)


def test_posts_the_body_to_responses():
    client, session = make_client(FakeResponse(payload={"status": "completed"}))
    assert client.create_response(BODY, "Transcription of a.pdf") == {"status": "completed"}
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", "https://api.test/v1/responses")
    assert kwargs["json"] == BODY
    assert kwargs["timeout"] == (15, 90)


def test_session_sends_bearer_token():
    client = OpenAIClient("  secret  ")
    assert client._session.headers["Authorization"] == "Bearer secret"
    assert client.base_url == "https://api.openai.com/v1"


def test_retries_rate_limits_honoring_retry_after():
    client, session = make_client(
        error(429, "slow down", "rate_limit_exceeded", headers={"Retry-After": "7"}),
        error(503, "overloaded"),
        FakeResponse(payload={"status": "completed"}),
    )
    assert client.create_response(BODY, "t")["status"] == "completed"
    assert len(session.calls) == 3
    assert client.delays[0] == 7.0


def test_retries_failed_responses_unless_the_request_is_bad():
    stream_ended = {"status": "failed", "error": {"message": "Stream ended before a terminal response event"}}
    client, session = make_client(
        FakeResponse(payload=stream_ended),
        FakeResponse(payload={"status": "failed", "error": {"code": "server_error", "message": "oops"}}),
        FakeResponse(payload={"status": "completed"}),
    )
    assert client.create_response(BODY, "t")["status"] == "completed"
    assert len(session.calls) == 3

    bad_image = {"status": "failed", "error": {"code": "invalid_image", "message": "unreadable"}}
    client, session = make_client(FakeResponse(payload=bad_image))
    assert client.create_response(BODY, "t") == bad_image  # parse_response reports it
    assert len(session.calls) == 1

    client, _ = make_client(*[FakeResponse(payload=stream_ended)] * MAX_ATTEMPTS)
    with pytest.raises(RetryableAPIError, match="t: response failed: Stream ended"):
        client.create_response(BODY, "t")


def test_retries_network_errors_then_gives_up():
    client, _ = make_client(*[requests.ConnectionError("reset")] * MAX_ATTEMPTS)
    with pytest.raises(RetryableAPIError, match="t: network error"):
        client.create_response(BODY, "t")
    assert len(client.delays) == MAX_ATTEMPTS - 1


def test_read_timeout_is_not_retried():
    client, session = make_client(requests.ReadTimeout("slow"))
    with pytest.raises(APIError, match="no response after 90s"):
        client.create_response(BODY, "t")
    assert len(session.calls) == 1


def test_auth_failure_is_fatal_and_names_the_provider():
    client, session = make_client(error(401, "Incorrect API key"), label="OpenRouter")
    with pytest.raises(FatalAPIError, match="OpenRouter rejected your API key"):
        client.create_response(BODY, "t")
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        error(429, "no credits", "credit_balance_exhausted"),
        error(429, "quota", "insufficient_quota"),
        error(402, "Insufficient credits"),
    ],
)
def test_exhausted_credit_is_fatal(response):
    client, session = make_client(response)
    with pytest.raises(FatalAPIError, match="out of credits or over quota"):
        client.create_response(BODY, "t")
    assert len(session.calls) == 1


def test_unknown_model_and_forbidden_are_fatal():
    for response in (error(404, "no such model", "model_not_found"), error(403, "unsupported region")):
        client, _ = make_client(response)
        with pytest.raises(FatalAPIError, match="refused the request"):
            client.create_response(BODY, "t")


def test_moderation_fails_only_the_file():
    client, _ = make_client(error(403, "flagged", "image_content_policy_violation"))
    with pytest.raises(APIError, match="t: HTTP 403: flagged") as info:
        client.create_response(BODY, "t")
    assert not isinstance(info.value, FatalAPIError)


def test_client_errors_report_detail():
    client, _ = make_client(error(400, "Invalid file data"))
    with pytest.raises(APIError, match="t: HTTP 400: Invalid file data"):
        client.create_response(BODY, "t")
    client, _ = make_client(FakeResponse(413, text="too big"))
    with pytest.raises(APIError, match="limit is 50 MB"):
        client.create_response(BODY, "t")
    client, _ = make_client(FakeResponse(418, text="teapot"))
    with pytest.raises(APIError, match="HTTP 418: teapot"):
        client.create_response(BODY, "t")


def test_invalid_json_is_retried():
    client, session = make_client(
        FakeResponse(200, None, text="<html>"),
        FakeResponse(200, ["not", "a", "dict"]),
        FakeResponse(payload={"status": "completed"}),
    )
    assert client.create_response(BODY, "t")["status"] == "completed"
    assert len(session.calls) == 3


def test_other_request_errors_are_not_retried():
    client, _ = make_client(requests.exceptions.InvalidURL("bad"))
    with pytest.raises(APIError, match="t: bad"):
        client.create_response(BODY, "t")


def test_cancelled_client_stops_before_calling():
    client, session = make_client(FakeResponse(payload={}))
    client.stop_event.set()
    with pytest.raises(Cancelled):
        client.create_response(BODY, "t")
    assert session.calls == []


def test_real_sleep_wakes_on_cancel():
    client = OpenAIClient("k")
    client.stop_event.set()
    with pytest.raises(Cancelled):
        client.sleep(30)


def test_empty_api_key_rejected():
    with pytest.raises(FatalAPIError):
        OpenAIClient("  ")
