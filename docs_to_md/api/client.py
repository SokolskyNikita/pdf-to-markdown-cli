import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any

import backoff
import filetype
import requests
from ratelimit import limits, sleep_and_retry

from docs_to_md.api.models import MarkerStatus, StatusEnum, SubmitResponse, SUPPORTED_MIME_TYPES
from docs_to_md.utils.exceptions import APIError
from docs_to_md.utils.file_utils import FileIO

# Constants
MAX_REQUESTS_PER_MINUTE = 150
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class MarkerClient:
    """Client for interacting with the Marker API."""

    BASE_URL = "https://www.datalab.to/api/v1/marker"

    def __init__(self, api_key: str):
        """
        Initialize the API client.
        
        Args:
            api_key: API key for authentication
            
        Raises:
            APIError: If API key is not provided or invalid
        """
        # Check for empty API key
        if not api_key:
            raise APIError("API key is required")
            
        # Basic validation - API keys should typically be alphanumeric
        # and have a reasonable length. The exact format depends on Marker's specs.
        api_key = api_key.strip()  # Remove accidental whitespace
        if len(api_key) < 8:  # Assuming a minimum sensible length
            raise APIError("API key appears to be too short")
            
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
        max_pages: Optional[int] = None,
    ) -> Optional[str]:
        """
        Submit a file for conversion.
        
        Args:
            file_path: Path to the file to submit
            output_format: Desired output format (markdown, json, html)
            langs: Comma-separated OCR languages
            use_llm: Whether to use LLM for enhanced processing
            strip_existing_ocr: Whether to redo OCR processing
            disable_image_extraction: Whether to disable image extraction
            force_ocr: Whether to force OCR on all pages
            paginate: Whether to add page delimiters
            max_pages: Maximum pages to process
            
        Returns:
            Request ID if successful, None otherwise
            
        Raises:
            APIError: If file is invalid or API request fails
        """
        try:
            # Validate file exists
            if not file_path.exists():
                raise APIError(f"File not found: {file_path}")

            # Read file and check type
            file_data = FileIO.read_file(file_path)
            kind = filetype.guess(file_data)
            if not kind or kind.mime not in SUPPORTED_MIME_TYPES:
                raise APIError(f"Unsupported file type: {kind.mime if kind else 'unknown'}")

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
            # Add max_pages only if it's provided
            if max_pages is not None:
                files['max_pages'] = (None, max_pages)

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
                logger.error(f"API request failed: {submit_response.error or 'Unknown error'}")
                return None

            logger.info(f"Successfully submitted file. Request ID: {submit_response.request_id}")
            return submit_response.request_id

        except Exception as e:
            logger.error(f"Error submitting file {file_path}: {e}")
            return None

    @sleep_and_retry
    @limits(calls=MAX_REQUESTS_PER_MINUTE, period=60)
    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, json.JSONDecodeError),
        max_tries=MAX_RETRIES
    )
    def check_status(self, request_id: str) -> Optional[MarkerStatus]:
        """
        Check the status of a conversion request.
        
        Args:
            request_id: Request ID to check
            
        Returns:
            MarkerStatus object with current status, or None if request fails
        """
        if not request_id:
            logger.error("Cannot check status: empty request_id provided")
            return None
            
        try:
            # Make API request with timeout
            response = requests.get(
                f"{self.BASE_URL}/{request_id}",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT
            )
            
            # Handle non-200 responses properly
            if response.status_code != 200:
                logger.error(f"API returned status code {response.status_code} for request {request_id}")
                if response.status_code == 404:
                    return MarkerStatus(status=StatusEnum.PROCESSING, error="Request not found")
                elif response.status_code == 401:
                    return MarkerStatus(status=StatusEnum.FAILED, error="Authentication failed")
                elif response.status_code == 429:
                    return MarkerStatus(status=StatusEnum.PROCESSING, error="Rate limit exceeded")
                return None
                
            # Parse response JSON
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response for request {request_id}: {e}")
                return None

            # Handle empty response
            if not data:
                logger.error(f"Empty response for request {request_id}")
                return None

            # Validate and create status object
            try:
                status = MarkerStatus.model_validate(data)
                return status
            except Exception as e:
                logger.error(f"Failed to parse status response for {request_id}: {e}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout checking status for {request_id}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error checking status for {request_id}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error checking status for {request_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking status for {request_id}: {e}")
            return None
            
    def __enter__(self):
        """Support for context manager."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources if needed."""
        pass  # No cleanup needed for API client 