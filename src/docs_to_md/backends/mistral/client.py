"""HTTP client for Mistral's OCR API.

It reuses ``OpenAIClient``'s session handling and retry loop, since Mistral's
API follows the same conventions, and classifies Mistral's own error bodies.

Reference: https://docs.mistral.ai/api/endpoint/ocr
"""

from __future__ import annotations

import threading
from typing import Any

import requests

from docs_to_md.backends.openai.client import RETRYABLE_STATUS_CODES, OpenAIClient, _retry_after
from docs_to_md.errors import APIError, FatalAPIError, RetryableAPIError

DEFAULT_BASE_URL = "https://api.mistral.ai/v1"


def _message(value: Any) -> str:
    """Flatten Mistral's error messages, which may be validation-error lists."""
    if isinstance(value, dict):
        return _message(value.get("detail", value.get("message", value)))
    if isinstance(value, list):
        return "; ".join(
            f"{'.'.join(str(p) for p in item.get('loc', [])[1:])}: {item.get('msg')}".lstrip(": ")
            if isinstance(item, dict)
            else str(item)
            for item in value
        )
    return str(value)


def _error(response: requests.Response) -> tuple[str, str]:
    """The (message, type) of an error response.

    Mistral answers with ``{"object": "error", "message": ..., "type": ...}``, or
    ``{"detail": ...}`` for authentication and validation errors.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:300] or response.reason or "", ""
    if not isinstance(body, dict):
        return str(body)[:300], ""
    return _message(body.get("message", body.get("detail", body)))[:300], str(body.get("type") or "")


class MistralClient(OpenAIClient):
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        stop_event: threading.Event | None = None,
        timeout: float = 3600.0,
    ):
        super().__init__(api_key, base_url, stop_event, timeout, label="Mistral")

    def ocr(self, body: dict[str, Any], what: str) -> dict[str, Any]:
        """POST /ocr, retrying transient failures, and return the payload."""
        return self.post("/ocr", body, what)

    def _check_response(self, response: requests.Response, what: str) -> dict[str, Any]:
        status = response.status_code
        if status < 400:
            return super()._check_response(response, what)
        message, kind = _error(response)
        detail = f"HTTP {status}: {message}".rstrip(": ")
        if status == 401:
            raise FatalAPIError(f"Authentication failed: Mistral rejected your API key ({detail}).", status)
        if status == 402:
            raise FatalAPIError(f"Mistral account is out of credits ({detail}).", status)
        if status == 403 or kind == "invalid_model":
            raise FatalAPIError(f"Mistral refused the request ({detail}).", status)
        if status in RETRYABLE_STATUS_CODES:
            raise RetryableAPIError(f"{what}: {detail}", status, _retry_after(response))
        if status == 413:
            raise APIError(f"{what}: file is too large for the API (limit is 50 MB)", status)
        raise APIError(f"{what}: {detail}", status)
