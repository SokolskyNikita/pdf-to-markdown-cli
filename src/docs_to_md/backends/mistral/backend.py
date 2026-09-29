"""Convert chunks with Mistral's OCR API: one synchronous request per chunk."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from docs_to_md.assemble import ChunkOutput, join_pages
from docs_to_md.backends.base import Backend, BackendInfo, CancelCheck
from docs_to_md.backends.mistral.client import MistralClient
from docs_to_md.backends.mistral.models import (
    DEFAULT_MODEL,
    INPUT_MIME_TYPES,
    OUTPUT_FORMATS,
    OCRRequest,
    parse_response,
    requested_pages,
)
from docs_to_md.pdf import Chunk

if TYPE_CHECKING:
    from docs_to_md.config import Config


class MistralBackend(Backend):
    info = BackendInfo(
        name="mistral",
        label="Mistral",
        input_extensions=frozenset(INPUT_MIME_TYPES),
        output_formats=OUTPUT_FORMATS,
        max_upload_bytes=50 * 1024 * 1024,
        default_model=DEFAULT_MODEL,
        api_key_env_vars=("MISTRAL_API_KEY",),
        api_key_url="https://console.mistral.ai/api-keys",
    )

    def __init__(self, config: Config, client: MistralClient):
        self.config = config
        self.client = client

    @classmethod
    def from_config(cls, config: Config, stop_event: threading.Event) -> MistralBackend:
        return cls(config, MistralClient(config.api_key or "", stop_event=stop_event, timeout=config.timeout))

    def request_for(self, chunk: Chunk) -> OCRRequest:
        """The request for ``chunk``.

        Split PDFs already contain only the selected pages, so page selection is
        sent only for documents uploaded whole.
        """
        config = self.config
        return OCRRequest(
            model=config.model or DEFAULT_MODEL,
            include_images=not config.disable_image_extraction,
            pages=None if chunk.pages else requested_pages(config.page_range, config.max_pages),
            extra=dict(config.extra_options),
        )

    def convert(self, chunk: Chunk, check_cancelled: CancelCheck) -> ChunkOutput:
        request = self.request_for(chunk)
        body = request.body(chunk.path)
        check_cancelled()
        data = self.client.ocr(body, f"OCR of {chunk.path.name}")
        result = parse_response(data, request.model, request.include_images)
        return ChunkOutput(
            # A whole document's pages are numbered by the API.
            pages=chunk.pages or result.indexes,
            content=join_pages(result.pages, self.config.output_format, self.config.paginate),
            images=result.images,
            page_count=result.pages_processed,
            cost_cents=result.cost_cents or 0.0,
        )
