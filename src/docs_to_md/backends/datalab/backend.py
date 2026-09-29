"""Convert chunks with the hosted Datalab Convert API: submit, then poll."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from docs_to_md.assemble import ChunkOutput
from docs_to_md.backends.base import Backend, BackendInfo, CancelCheck
from docs_to_md.backends.datalab.client import DatalabClient
from docs_to_md.backends.datalab.models import (
    INPUT_MIME_TYPES,
    MODES,
    OUTPUT_FORMATS,
    ConvertOptions,
    ConvertResult,
)
from docs_to_md.console import format_elapsed
from docs_to_md.errors import APIError, RetryableAPIError
from docs_to_md.pdf import Chunk

if TYPE_CHECKING:
    from docs_to_md.config import Config

logger = logging.getLogger(__name__)

INITIAL_POLL_SECONDS = 2.0
MAX_POLL_SECONDS = 15.0
MAX_RATE_LIMIT_RESUBMITS = 3


class DatalabBackend(Backend):
    info = BackendInfo(
        name="datalab",
        label="Datalab",
        input_extensions=frozenset(INPUT_MIME_TYPES),
        output_formats=OUTPUT_FORMATS,
        modes=MODES,
        max_upload_bytes=200 * 1024 * 1024,
        api_key_env_vars=("DATALAB_API_KEY", "MARKER_PDF_KEY"),
        api_key_url="https://www.datalab.to/app/keys",
    )

    def __init__(self, config: Config, client: DatalabClient):
        self.config = config
        self.client = client

    @classmethod
    def from_config(cls, config: Config, stop_event: threading.Event) -> DatalabBackend:
        return cls(config, DatalabClient(config.api_key or "", stop_event=stop_event))

    def options_for(self, chunk: Chunk) -> ConvertOptions:
        """Form fields for ``chunk``.

        Split PDFs already contain only the selected pages, so ``page_range`` and
        ``max_pages`` are sent only for documents uploaded whole.
        """
        config = self.config
        select_remotely = not chunk.pages
        return ConvertOptions(
            output_format=config.output_format,
            mode=config.mode,
            paginate=config.paginate,
            disable_image_extraction=config.disable_image_extraction,
            disable_image_captions=config.disable_image_captions,
            skip_cache=config.skip_cache,
            page_range=config.page_range if select_remotely else None,
            max_pages=config.max_pages if select_remotely else None,
            extra=dict(config.extra_options),
        )

    def convert(self, chunk: Chunk, check_cancelled: CancelCheck) -> ChunkOutput:
        options = self.options_for(chunk)
        deadline = time.monotonic() + self.config.timeout
        for attempt in range(MAX_RATE_LIMIT_RESUBMITS + 1):
            check_cancelled()
            request_id = self.client.submit(chunk.path, options)
            result = self._wait_for_result(request_id, deadline, check_cancelled)
            if result.status == "complete" and result.success is not False:
                content = result.content_for(self.config.output_format)
                if content is None:
                    raise APIError(f"the API returned no {self.config.output_format} output")
                return ChunkOutput(
                    pages=chunk.pages,
                    content=content,
                    images=result.images,
                    page_count=result.page_count or len(chunk.pages),
                    cost_cents=result.cost_cents or 0.0,
                )
            error = result.error or f"conversion {result.status}"
            # Page throughput limits surface as failed results, not HTTP 429.
            if "rate limit" in error.lower() and attempt < MAX_RATE_LIMIT_RESUBMITS:
                logger.debug("Request %s hit a rate limit; resubmitting", request_id)
                self.client.sleep(30.0 * (attempt + 1))
                continue
            raise APIError(error)
        raise AssertionError("unreachable")

    def _wait_for_result(
        self, request_id: str, deadline: float, check_cancelled: CancelCheck
    ) -> ConvertResult:
        delay = INITIAL_POLL_SECONDS
        while True:
            check_cancelled()
            try:
                result = self.client.get_result(request_id)
                if result.status != "processing":
                    return result
            except RetryableAPIError as e:
                logger.debug("Polling %s: %s", request_id, e)
            if time.monotonic() + delay > deadline:
                raise APIError(
                    f"timed out after {format_elapsed(self.config.timeout)} waiting for "
                    f"request {request_id} (raise --timeout for very large jobs)"
                )
            self.client.sleep(delay)
            delay = min(delay * 1.5, MAX_POLL_SECONDS)
