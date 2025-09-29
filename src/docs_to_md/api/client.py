import json
import logging
from pathlib import Path
from typing import Optional

import backoff
import filetype
import requests
from ratelimit import limits, sleep_and_retry

from docs_to_md.api.models import (
    MarkerStatus,
    StatusEnum,
    SubmitResponse,
    SUPPORTED_MIME_TYPES,
)
from docs_to_md.utils.exceptions import APIError
from docs_to_md.utils.file_utils import FileIO

# Client-side constants
MAX_REQUESTS_PER_MINUTE = 150
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class MarkerClient:
    BASE_MARKER_API_ENDPOINT = "https://www.datalab.to/api/v1/marker"

    # See datalab_marker_api_docs.md#authentication for API key details
    def __init__(self, api_key: str):
        if not api_key or not api_key.strip():
            raise APIError("API key is required")

        self.headers = {"X-Api-Key": api_key.strip()}

    @sleep_and_retry
    @limits(calls=MAX_REQUESTS_PER_MINUTE, period=60)
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=MAX_RETRIES,
    )
    def submit_file(
        self,
        file_path: Path,
        output_format: str = "markdown",
        langs: str = "English",
        use_llm: bool = False,
        strip_existing_ocr: bool = False,
        disable_image_extraction: bool = False,
        force_ocr: bool = False,
        paginate: bool = False,
        max_pages: Optional[int] = None,
    ) -> Optional[str]:
        """Submit a file for conversion via the Marker API.
        See datalab_marker_api_docs.md#marker for API parameter details.
        """
        try:
            if not file_path.exists():
                raise APIError(f"File not found: {file_path}")

            file_data = FileIO.read_file(file_path)
            kind = filetype.guess(file_data)

            # Supported types listed in datalab_marker_api_docs.md#supported-file-types
            if not kind or kind.mime not in SUPPORTED_MIME_TYPES:
                raise APIError(
                    f"Unsupported file type: {kind.mime if kind else 'unknown'}"
                )

            form_data = {
                "file": (file_path.name, file_data, kind.mime),
                "langs": (None, langs),
                "output_format": (None, output_format),
            }
            
            # Add boolean parameters with proper serialization
            if force_ocr:
                form_data["force_ocr"] = (None, "true")
            if paginate:
                form_data["paginate"] = (None, "true")
            if strip_existing_ocr:
                form_data["strip_existing_ocr"] = (None, "true")
            if disable_image_extraction:
                form_data["disable_image_extraction"] = (None, "true")
            if use_llm:
                form_data["use_llm"] = (None, "true")
            
            # Add max_pages only if it has a value
            if max_pages is not None:
                form_data["max_pages"] = (None, str(max_pages))

            response = requests.post(
                self.BASE_MARKER_API_ENDPOINT,
                files=form_data,
                headers=self.headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()  # Default handling for HTTP errors,
            submit_response = SubmitResponse.model_validate(response.json())

            if not submit_response.success:
                logger.error(
                    f"API request failed: {submit_response.error or 'Unknown error'}"
                )
                return None

            logger.info(
                f"Successfully submitted file {file_path.name}. Request ID: {submit_response.request_id}"
            )
            return submit_response.request_id

        except Exception as e:
            logger.error(f"Error submitting file {file_path}: {e}")
            return None

    def _handle_status_error(
        self, status_code: int, request_id: str
    ) -> Optional[MarkerStatus]:
        """Handle non-200 status codes from the check_status endpoint."""
        logger.error(f"API returned status code {status_code} for request {request_id}")
        # Specific handling for non-fatal polling errors
        if status_code == 404:
            # Treat not found as still processing, might appear later
            return MarkerStatus(status=StatusEnum.PROCESSING, error="Request not found")
        elif status_code == 401:
            return MarkerStatus(status=StatusEnum.FAILED, error="Authentication failed")
        elif status_code == 429:
            # Treat rate limit as still processing, should retry later
            return MarkerStatus(
                status=StatusEnum.PROCESSING, error="Rate limit exceeded"
            )
        # For other non-200 errors, return None to indicate failure to get status
        return None

    @sleep_and_retry
    @limits(calls=MAX_REQUESTS_PER_MINUTE, period=60)
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=MAX_RETRIES,
    )
    def check_status(self, request_id: str) -> Optional[MarkerStatus]:
        """
        Check the status of a conversion request.
        See datalab_marker_api_docs.md#marker for polling details.

        Returns:
            MarkerStatus object with current status, or None if the check fails.
        """
        if not request_id:
            logger.error("Empty Marker request ID provided, skipping status check")
            return None

        try:
            response = requests.get(
                f"{self.BASE_MARKER_API_ENDPOINT}/{request_id}",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code != 200:
                return self._handle_status_error(response.status_code, request_id)

            data = response.json()
            # Handle potential empty response from API
            if not data:
                logger.error(f"Empty response for request {request_id}")
                return None

            status = MarkerStatus.model_validate(data)
            return status

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response for request {request_id}: {e}")
            return None
        except (
            requests.exceptions.RequestException
        ) as e:  # Consolidated network/request errors
            logger.error(f"Request error checking status for {request_id}: {e}")
            return None
        except Exception as e:  # Catch-all for validation or other unexpected errors
            logger.error(f"Unexpected error checking status for {request_id}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # No specific cleanup needed for this client
        pass
