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
    OCRResult,
    cost_cents,
    parse_response,
    requested_pages,
)
from docs_to_md.errors import APIError
from docs_to_md.pdf import Chunk
from docs_to_md.spreads import join_halves, spread_halves

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
        splits_spreads=True,
    )

    def __init__(self, config: Config, client: MistralClient):
        self.config = config
        self.client = client

    @classmethod
    def from_config(cls, config: Config, stop_event: threading.Event) -> MistralBackend:
        return cls(config, MistralClient(config.api_key or "", stop_event=stop_event, timeout=config.timeout))

    @classmethod
    def estimate_cents(cls, config: Config, pages: int) -> float | None:
        return cost_cents(config.model or DEFAULT_MODEL, pages)

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

    def _ocr(self, chunk: Chunk, check_cancelled: CancelCheck) -> OCRResult:
        request = self.request_for(chunk)
        body = request.body(chunk.path)
        check_cancelled()
        data = self.client.ocr(body, f"OCR of {chunk.path.name}")
        return parse_response(data, request.model, request.include_images)

    def convert(self, chunk: Chunk, check_cancelled: CancelCheck) -> ChunkOutput:
        if self.config.split_spreads and chunk.pages:
            # Each half of a two-page scan is billed as a page of its own.
            with spread_halves(chunk) as (halves, counts):
                result = self._ocr(halves, check_cancelled)
            if len(result.pages) != len(halves.pages):
                raise APIError(f"the API returned {len(result.pages)} pages for {len(halves.pages)}")
            pages = join_halves(result.pages, counts)
        else:
            result = self._ocr(chunk, check_cancelled)
            pages = result.pages
        return ChunkOutput(
            # A whole document's pages are numbered by the API.
            pages=chunk.pages or result.indexes,
            content=join_pages(pages, self.config.output_format, self.config.paginate),
            images=result.images,
            page_count=len(pages),
            cost_cents=result.cost_cents or 0.0,
        )
