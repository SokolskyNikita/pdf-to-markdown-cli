"""HTTP client for the OpenAI Responses API, direct or through OpenRouter.

References:
- https://developers.openai.com/api/docs/api-reference/responses
- https://openrouter.ai/docs/api_reference/responses/overview
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Any

import requests

from docs_to_md.errors import APIError, Cancelled, FatalAPIError, RetryableAPIError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
CONNECT_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 6
MAX_BACKOFF_SECONDS = 60.0
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
# 429s that won't clear up by waiting.
# https://developers.openai.com/api/docs/guides/error-codes
QUOTA_ERROR_CODES = {
    "insufficient_quota",
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
}


def _error(response: requests.Response) -> tuple[str, str]:
    """The (message, code) of an API error response."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:300] or response.reason or "", ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or ""), str(error.get("code") or error.get("type") or "")
    return str(body)[:300], ""


def _retry_after(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        stop_event: threading.Event | None = None,
        timeout: float = 3600.0,
        label: str = "OpenAI",
    ):
        if not api_key or not api_key.strip():
            raise FatalAPIError("API key is required")
        self.base_url = base_url.rstrip("/")
        self.label = label
        self.headers = {"Authorization": f"Bearer {api_key.strip()}"}
        self.stop_event = stop_event or threading.Event()
        self.timeout = timeout
        self._local = threading.local()

    @property
    def _session(self) -> requests.Session:
        # requests.Session is not guaranteed thread-safe; keep one per thread.
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.headers)
            self._local.session = session
        return session

    def sleep(self, seconds: float) -> None:
        """Sleep that wakes up immediately when the run is cancelled."""
        if self.stop_event.wait(seconds):
            raise Cancelled("Interrupted")

    def _backoff(self, attempt: int, error: RetryableAPIError) -> float:
        if error.retry_after is not None:
            return min(error.retry_after, MAX_BACKOFF_SECONDS)
        return min(MAX_BACKOFF_SECONDS, 2.0 * (2**attempt)) * random.uniform(0.75, 1.25)

    def _check_response(self, response: requests.Response, what: str) -> dict[str, Any]:
        status = response.status_code
        if status < 400:
            try:
                data = response.json()
            except ValueError as e:
                raise RetryableAPIError(f"{what}: invalid JSON in response ({e})", status) from e
            if not isinstance(data, dict):
                raise RetryableAPIError(f"{what}: unexpected response payload", status)
            return data
        message, code = _error(response)
        detail = f"HTTP {status}: {message}".rstrip(": ")
        if status == 401:
            raise FatalAPIError(
                f"Authentication failed: {self.label} rejected your API key ({detail}).", status
            )
        if status == 402 or (status == 429 and code in QUOTA_ERROR_CODES):
            raise FatalAPIError(f"{self.label} account is out of credits or over quota ({detail}).", status)
        if status == 403 and code.endswith("content_policy_violation"):
            # OpenRouter's moderation verdict on this document, not the account.
            raise APIError(f"{what}: {detail}", status)
        if status == 403 or (status == 404 and code == "model_not_found"):
            raise FatalAPIError(f"{self.label} refused the request ({detail}).", status)
        if status in RETRYABLE_STATUS_CODES:
            raise RetryableAPIError(f"{what}: {detail}", status, _retry_after(response))
        if status == 413:
            raise APIError(f"{what}: file is too large for the API (limit is 50 MB)", status)
        raise APIError(f"{what}: {detail}", status)

    def create_response(self, body: dict[str, Any], what: str) -> dict[str, Any]:
        """POST /responses, retrying transient failures, and return the payload."""
        last_error: RetryableAPIError | None = None
        for attempt in range(MAX_ATTEMPTS):
            if self.stop_event.is_set():
                raise Cancelled("Interrupted")
            try:
                response = self._session.post(
                    f"{self.base_url}/responses",
                    json=body,
                    timeout=(CONNECT_TIMEOUT_SECONDS, self.timeout),
                )
                return self._check_response(response, what)
            except requests.ReadTimeout as e:
                raise APIError(f"{what}: no response after {self.timeout:.0f}s (raise --timeout)") from e
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as e:
                last_error = RetryableAPIError(f"{what}: network error ({e})")
            except RetryableAPIError as e:
                last_error = e
            except requests.RequestException as e:
                raise APIError(f"{what}: {e}") from e
            if attempt < MAX_ATTEMPTS - 1:
                delay = self._backoff(attempt, last_error)
                logger.debug("%s; retrying in %.1fs", last_error, delay)
                self.sleep(delay)
        assert last_error is not None
        raise last_error
