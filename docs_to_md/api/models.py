from enum import Enum
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass

from pydantic import BaseModel


class StatusEnum(str, Enum):
    """Enum for API status values."""
    COMPLETE = "complete"
    PROCESSING = "processing"
    FAILED = "failed"


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


@dataclass
class ApiParams:
    """Parameters for the Marker API submit call."""
    output_format: str = "markdown"
    langs: str = "English"
    use_llm: bool = False
    strip_existing_ocr: bool = False
    disable_image_extraction: bool = False
    force_ocr: bool = False
    paginate: bool = False
    max_pages: Optional[int] = None


# Supported mime types according to API docs
SUPPORTED_MIME_TYPES: Set[str] = {
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