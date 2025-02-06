import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import backoff
import filetype
import requests
from pydantic import BaseModel
from ratelimit import limits, sleep_and_retry

# Constants
MAX_REQUESTS_PER_MINUTE = 150
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3



class StatusEnum(str, Enum):
    COMPLETE = "complete"
    PROCESSING = "processing"

class MarkerStatus(BaseModel):
    """Model for API status response."""
    status: StatusEnum  # Indicates the status of the request (`complete`, or `processing`).
    output_format: Optional[str] = None  # The requested output format, `json`, `html`, or `markdown`.
    success: Optional[bool] = None  # Indicates if the request completed successfully. `True` or `False`.
    error: Optional[str] = None  # If there was an error, this contains the error message.
    markdown: Optional[str] = None  # The output from the file if `output_format` is `markdown`.
    json_data: Optional[Dict[str, Any]] = None  # The output from the file if `output_format` is `json`.
    images: Optional[Dict[str, str]] = None  # Dictionary of image filenames (keys) and base64 encoded images (values).
    meta: Optional[Dict[str, Any]] = None  # Metadata about the markdown conversion.
    page_count: Optional[int] = None  # Number of pages that were converted.

class SubmitResponse(BaseModel):
    """Model for API submit response."""
    success: bool
    error: Optional[str] = None
    request_id: str
    request_check_url: Optional[str] = None

class MarkerClient:
    """Simple client for interacting with the Marker API."""

    BASE_URL = "https://www.datalab.to/api/v1/marker"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required")
        self.headers = {"X-Api-Key": api_key}

    @sleep_and_retry
    @limits(calls=MAX_REQUESTS_PER_MINUTE, period=60)
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=MAX_RETRIES
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
    ) -> Optional[str]:
        """Submit a file for conversion. Returns request ID if successful."""
        try:
            # Validate file exists
            if not file_path.exists():
                raise ValueError(f"File not found: {file_path}")

            # Read file and check type
            file_data = file_path.read_bytes()
            kind = filetype.guess(file_data)
            if not kind or kind.mime not in SUPPORTED_MIME_TYPES:
                raise ValueError(f"Unsupported file type: {kind.mime if kind else 'unknown'}")

            # Build form data
            files = {
                'file': (file_path.name, file_data, kind.mime),
                'langs': (None, langs),
                'force_ocr': (None, force_ocr),
                'paginate': (None, paginate),
                'strip_existing_ocr': (None, strip_existing_ocr),
                'disable_image_extraction': (None, disable_image_extraction),
                'use_llm': (None, use_llm),
                'output_format': (None, output_format),
            }

            # Send request
            response = requests.post(
                self.BASE_URL,
                files=files,
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()

            # Parse response
            data = response.json()

            submit_response = SubmitResponse.model_validate(data)

            if not submit_response.success:
                logging.error(f"API request failed: {submit_response.error or 'Unknown error'}")
                return None

            logging.info(f"Successfully submitted file. Request ID: {submit_response.request_id}")
            return submit_response.request_id

        except Exception as e:
            logging.error(f"Error submitting file {file_path}: {e}")
            return None

    @sleep_and_retry
    @limits(calls=MAX_REQUESTS_PER_MINUTE, period=60)
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=MAX_RETRIES
    )
    def check_status(self, request_id: str) -> Optional[MarkerStatus]:
        """Check the status of a conversion request."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/{request_id}",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()

            data = response.json()

            # Handle 404 or missing request
            if response.status_code == 404 or not data:
                logging.error(f"Request {request_id} not found")
                return None

            # Validate and create status object
            try:
                status = MarkerStatus.model_validate(data)

                return status
            except Exception as e:
                logging.error(f"Failed to parse status response for {request_id}: {e}")

                return None

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error checking status for {request_id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error checking status for {request_id}: {e}")
            return None

# Supported mime types according to API docs
SUPPORTED_MIME_TYPES = {
    # PDF
    'application/pdf',
    # Word documents
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    # Powerpoint
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    # Images
    'image/png',
    'image/jpeg',
    'image/webp',
    'image/gif',
    'image/tiff',
    'image/jpg'
}
