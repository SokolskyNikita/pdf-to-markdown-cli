"""Transcribe chunks with an OpenAI vision model (GPT-Luna by default), called
directly or through OpenRouter. Both speak the same Responses API."""

from __future__ import annotations

import dataclasses
import logging
import threading
from typing import TYPE_CHECKING, Any, ClassVar

from docs_to_md.assemble import ChunkOutput, join_pages
from docs_to_md.backends.base import Backend, BackendInfo, CancelCheck
from docs_to_md.backends.openai.client import DEFAULT_BASE_URL, OpenAIClient
from docs_to_md.backends.openai.models import (
    DEFAULT_MODE,
    DEFAULT_MODEL,
    INPUT_MIME_TYPES,
    MODES,
    OUTPUT_FORMATS,
    REASONING_EFFORT,
    TranscribeRequest,
    parse_response,
)
from docs_to_md.errors import APIError
from docs_to_md.pdf import Chunk

if TYPE_CHECKING:
    from docs_to_md.config import Config

logger = logging.getLogger(__name__)

MAX_PAGE_COUNT_ATTEMPTS = 2


class OpenAIBackend(Backend):
    info = BackendInfo(
        name="openai",
        label="OpenAI",
        input_extensions=frozenset(INPUT_MIME_TYPES),
        output_formats=OUTPUT_FORMATS,
        modes=MODES,
        max_upload_bytes=50 * 1024 * 1024,
        chunk_size=5,
        default_model=DEFAULT_MODEL,
        api_key_env_vars=("OPENAI_API_KEY",),
        api_key_url="https://platform.openai.com/api-keys",
    )

    base_url = DEFAULT_BASE_URL
    extra_body: ClassVar[dict[str, Any]] = {}

    def __init__(self, config: Config, client: OpenAIClient):
        self.config = config
        self.client = client

    @classmethod
    def from_config(cls, config: Config, stop_event: threading.Event) -> OpenAIBackend:
        client = OpenAIClient(
            config.api_key or "",
            base_url=cls.base_url,
            stop_event=stop_event,
            timeout=config.timeout,
            label=cls.info.label,
        )
        return cls(config, client)

    def model_name(self) -> str:
        return self.config.model or self.info.default_model or DEFAULT_MODEL

    def request_for(self, chunk: Chunk) -> TranscribeRequest:
        config = self.config
        return TranscribeRequest(
            model=self.model_name(),
            output_format=config.output_format,
            page_count=len(chunk.pages) or 1,  # an image is one page
            reasoning_effort=REASONING_EFFORT[config.mode or DEFAULT_MODE],
            describe_figures=not config.disable_image_captions,
            extra=dict(config.extra_options),
        )

    def body_for(self, chunk: Chunk, request: TranscribeRequest) -> dict[str, Any]:
        return {**self.extra_body, **request.body(chunk.path)}  # --api-option wins

    def convert(self, chunk: Chunk, check_cancelled: CancelCheck) -> ChunkOutput:
        request = self.request_for(chunk)
        body = self.body_for(chunk, request)
        what = f"Transcription of {chunk.path.name}"
        cost = 0.0
        for _ in range(MAX_PAGE_COUNT_ATTEMPTS):
            check_cancelled()
            result = parse_response(self.client.create_response(body, what), request.model)
            cost += result.cost_cents or 0.0
            if len(result.pages) == request.page_count:
                break
            logger.debug("%s: got %d pages, expected %d", what, len(result.pages), request.page_count)
        else:
            raise APIError(
                f"the model returned {len(result.pages)} pages for {request.page_count}"
                " (try a smaller --chunk-size)"
            )
        return ChunkOutput(
            pages=chunk.pages,
            content=join_pages(result.pages, self.config.output_format, self.config.paginate),
            page_count=request.page_count,
            cost_cents=cost,
        )


class OpenRouterBackend(OpenAIBackend):
    """The same models through OpenRouter's OpenAI-compatible Responses API."""

    info = dataclasses.replace(
        OpenAIBackend.info,
        name="openrouter",
        label="OpenRouter",
        default_model=f"openai/{DEFAULT_MODEL}",
        api_key_env_vars=("OPENROUTER_API_KEY",),
        api_key_url="https://openrouter.ai/settings/keys",
    )
    base_url = "https://openrouter.ai/api/v1"
    # Hand PDFs to the model itself. Without this, OpenRouter falls back to a
    # paid OCR engine for models that can't read files, and the model never
    # sees the page images.
    extra_body: ClassVar[dict[str, Any]] = {"plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}

    def model_name(self) -> str:
        model = super().model_name()
        return model if "/" in model else f"openai/{model}"  # --model gpt-6-luna works on both
