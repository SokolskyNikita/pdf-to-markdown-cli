import requests
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from pydantic import BaseModel
import logging


class ConversionResult(BaseModel):
    request_id: str = None
    markdown: str = None
    json_data: dict = None
    images: Dict[str, str] = None


MIME_TYPES = {
    "PDF": "application/pdf",
    "DOC": "application/msword",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "PPT": "application/vnd.ms-powerpoint",
    "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

OUTPUT_EXTENSIONS = {
    "markdown": ".md",
    "json": ".json",
    "html": ".html",
    "txt": ".txt",
}


@dataclass
class ProcessingStatus:
    is_complete: bool
    result: Optional[dict] = None


@dataclass
class MarkerRequestBuilder:
    langs: str = "English"
    force_ocr: bool = False
    paginate: bool = False
    strip_existing_ocr: bool = False
    disable_image_extraction: bool = True
    use_llm: bool = False
    output_format: str = "markdown"
    skip_cache: bool = False
    max_pages: Optional[int] = None
    file_name: Optional[str] = None
    file_data: Optional[bytes] = None

    def build(self) -> dict:
        if not self.file_name or not self.file_data:
            raise ValueError("File name and data are required")

        file_ext = self.file_name.upper().split(".")[-1]
        if file_ext not in MIME_TYPES:
            raise ValueError(f"Unsupported file type: {file_ext}")

        return {
            "file": (self.file_name, self.file_data, MIME_TYPES[file_ext]),
            "langs": (None, self.langs),
            "force_ocr": (None, self.force_ocr),
            "paginate": (None, self.paginate),
            "strip_existing_ocr": (None, self.strip_existing_ocr),
            "disable_image_extraction": (None, self.disable_image_extraction),
            "use_llm": (None, self.use_llm),
            "output_format": (None, self.output_format),
            "skip_cache": (None, self.skip_cache),
            "max_pages": (None, self.max_pages) if self.max_pages is not None else None,
        }


class MarkerClient:
    def __init__(
        self, api_key: str, api_url: str = "https://www.datalab.to/api/v1/marker"
    ):
        self.api_url = api_url
        self.headers = {"X-Api-Key": api_key}

    def send_request(self, builder: MarkerRequestBuilder) -> Optional[Tuple[str, str]]:
        try:
            response = requests.post(
                self.api_url, files=builder.build(), headers=self.headers
            )

            if response.status_code == 200:
                data = response.json()
                if request_id := data.get("request_id"):
                    extension = OUTPUT_EXTENSIONS.get(
                        builder.output_format, ".txt"
                    )
                    return request_id, extension
            else:
                logging.error(f"API request failed with status code {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"Exception during API request: {str(e)}")
        return None

    def process_status(self, request_id: str) -> ProcessingStatus:
        try:
            response = requests.get(
                f"{self.api_url}/{request_id}", headers=self.headers
            )

            if response.status_code == 404:
                return ProcessingStatus(is_complete=True)

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "complete":
                    return ProcessingStatus(
                        is_complete=True, result=ConversionResult.model_validate(data)
                    )
                return ProcessingStatus(is_complete=False)
        except Exception:
            pass

        return ProcessingStatus(is_complete=False)
