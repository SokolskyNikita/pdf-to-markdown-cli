"""Validated runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docs_to_md.errors import ConfigurationError
from docs_to_md.models import MODES, SUPPORTED_FORMAT_EXTENSIONS, ConvertOptions
from docs_to_md.pdf import validate_page_range

DEFAULT_CHUNK_SIZE = 25
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT_SECONDS = 3600.0


@dataclass
class Config:
    inputs: list[Path]
    api_key: str | None = None
    output_dir: Path | None = None
    output_format: str = "markdown"
    mode: str | None = None
    paginate: bool = False
    disable_image_extraction: bool = False
    disable_image_captions: bool = False
    skip_cache: bool = False
    page_range: str | None = None
    max_pages: int | None = None
    chunk_size: int | None = DEFAULT_CHUNK_SIZE  # None disables splitting
    concurrency: int = DEFAULT_CONCURRENCY
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    overwrite: bool = False
    dry_run: bool = False
    reflow_markdown: bool = True
    extra_options: dict = field(default_factory=dict)

    def validate(self) -> Config:
        if not self.inputs:
            raise ConfigurationError("At least one input path is required")
        if not self.dry_run and not self.api_key:
            raise ConfigurationError(
                "No API key found. Set DATALAB_API_KEY (or MARKER_PDF_KEY), or pass "
                "--api-key. Get a key at https://www.datalab.to/app/keys"
            )
        if self.output_format not in SUPPORTED_FORMAT_EXTENSIONS:
            raise ConfigurationError(f"Unsupported output format: {self.output_format}")
        if self.mode is not None and self.mode not in MODES:
            raise ConfigurationError(f"Unsupported mode: {self.mode}")
        if self.chunk_size is not None and self.chunk_size < 1:
            raise ConfigurationError("--chunk-size must be at least 1")
        if self.max_pages is not None and self.max_pages < 1:
            raise ConfigurationError("--max-pages must be at least 1")
        if self.concurrency < 1:
            raise ConfigurationError("--concurrency must be at least 1")
        if self.timeout <= 0:
            raise ConfigurationError("--timeout must be positive")
        if self.page_range is not None:
            self.page_range = validate_page_range(self.page_range)
        if self.output_dir is not None:
            self.output_dir = self.output_dir.expanduser().resolve()
            if self.output_dir.exists() and not self.output_dir.is_dir():
                raise ConfigurationError(f"Output path is not a directory: {self.output_dir}")
        return self

    def convert_options(self, *, local_page_selection: bool) -> ConvertOptions:
        """API options for one request.

        PDFs are split locally, so their page selection is not sent to the API.
        """
        return ConvertOptions(
            output_format=self.output_format,
            mode=self.mode,
            paginate=self.paginate,
            disable_image_extraction=self.disable_image_extraction,
            disable_image_captions=self.disable_image_captions,
            skip_cache=self.skip_cache,
            page_range=None if local_page_selection else self.page_range,
            max_pages=None if local_page_selection else self.max_pages,
            extra=dict(self.extra_options),
        )
