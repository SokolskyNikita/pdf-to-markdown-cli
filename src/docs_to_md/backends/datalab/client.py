"""HTTP client for the Datalab Convert API.

Reference: https://documentation.datalab.to/api-reference/convert-document
"""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path
from typing import Any

import requests

from docs_to_md.backends.datalab.models import INPUT_MIME_TYPES, ConvertOptions, ConvertResult
from docs_to_md.errors import (
    APIError,
    Cancelled,
    FatalAPIError,
    RetryableAPIError,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.datalab.to/api/v1"
CONNECT_TIMEOUT_SECONDS = 15
UPLOAD_TIMEOUT_SECONDS = 600  # files may be up to 200 MB
READ_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 6
MAX_BACKOFF_SECONDS = 60.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504, 529}


def _error_detail(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:300] or response.reason or ""
    if isinstance(body, dict):
        for key in ("error", "detail", "message"):
            if body.get(key):
                return str(body[key])
    return str(body)[:300]


def _retry_after(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


class DatalabClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        stop_event: threading.Event | None = None,
    ):
        if not api_key or not api_key.strip():
            raise FatalAPIError("API key is required")
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key.strip()}
        self.stop_event = stop_event or threading.Event()
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

    def _check_response(
        self, response: requests.Response, what: str, authenticated: bool = True
    ) -> dict[str, Any]:
        status = response.status_code
        if status in (401, 403) and not authenticated:
            raise APIError(f"{what}: HTTP {status} (the download link was rejected or expired)", status)
        if status in (401, 403):
            raise FatalAPIError(
                f"Authentication failed: the Datalab API rejected your API key (HTTP {status}).",
                status,
            )
        if status == 402:
            raise FatalAPIError(
                f"Payment required: {_error_detail(response) or 'your Datalab account is out of credits'}.",
                status,
            )
        if status in RETRYABLE_STATUS_CODES:
            raise RetryableAPIError(
                f"{what}: HTTP {status} {_error_detail(response)}".strip(),
                status,
                _retry_after(response),
            )
        if status == 404:
            raise APIError(f"{what}: request not found or its result has expired.", status)
        if status == 413:
            raise APIError(f"{what}: file is too large for the API (limit is 200 MB).", status)
        if status >= 400:
            raise APIError(f"{what}: HTTP {status} {_error_detail(response)}".strip(), status)
        try:
            data = response.json()
        except ValueError as e:
            raise RetryableAPIError(f"{what}: invalid JSON in response ({e})", status) from e
        if not isinstance(data, dict):
            raise RetryableAPIError(f"{what}: unexpected response payload", status)
        return data

    def _call(self, what: str, send, authenticated: bool = True) -> dict[str, Any]:
        """Run ``send()`` with retries for transient failures."""
        last_error: RetryableAPIError | None = None
        for attempt in range(MAX_ATTEMPTS):
            if self.stop_event.is_set():
                raise Cancelled("Interrupted")
            try:
                return self._check_response(send(), what, authenticated)
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

    def submit(self, file_path: Path, options: ConvertOptions) -> str:
        """Upload a file for conversion and return its request ID."""
        mime_type = INPUT_MIME_TYPES.get(file_path.suffix.lower().lstrip("."))
        if not mime_type:
            raise APIError(f"Unsupported file type: {file_path.name}")
        form = options.to_form()

        def send() -> requests.Response:
            with open(file_path, "rb") as fh:
                return self._session.post(
                    f"{self.base_url}/convert",
                    files={"file": (file_path.name, fh, mime_type)},
                    data=form,
                    timeout=(CONNECT_TIMEOUT_SECONDS, UPLOAD_TIMEOUT_SECONDS),
                )

        data = self._call(f"Upload of {file_path.name} failed", send)
        if not data.get("success", True) or not data.get("request_id"):
            raise APIError(f"Upload of {file_path.name} was rejected: {data.get('error') or 'unknown error'}")
        logger.debug("Submitted %s as request %s", file_path.name, data["request_id"])
        return str(data["request_id"])

    def get_result(self, request_id: str) -> ConvertResult:
        """Fetch the current status (and output, once complete) of a request."""
        data = self._call(
            f"Status check for {request_id} failed",
            lambda: self._session.get(
                f"{self.base_url}/convert/{request_id}",
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            ),
        )
        result = ConvertResult.from_payload(data)
        if (
            result.status == "complete"
            and result.result_url
            and not (result.markdown or result.html or result.json)
        ):
            # Large results are served from a signed download URL instead.
            payload = self._call(
                f"Download of result {request_id} failed",
                lambda: requests.get(
                    result.result_url,
                    timeout=(CONNECT_TIMEOUT_SECONDS, UPLOAD_TIMEOUT_SECONDS),
                ),
                authenticated=False,
            )
            merged = {**data, **payload, "status": "complete"}
            result = ConvertResult.from_payload(merged)
        return result
