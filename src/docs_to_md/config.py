"""Validated runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docs_to_md.assemble import OUTPUT_EXTENSIONS
from docs_to_md.backends import DEFAULT_BACKEND, get_backend
from docs_to_md.errors import ConfigurationError
from docs_to_md.pdf import validate_page_range

DEFAULT_CHUNK_SIZE = 25
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT_SECONDS = 3600.0


@dataclass
class Config:
    inputs: list[Path]
    backend: str = DEFAULT_BACKEND
    api_key: str | None = None
    output_dir: Path | None = None
    output_format: str = "markdown"
    mode: str | None = None
    model: str | None = None  # None means the backend's default model
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
    extra_options: dict = field(default_factory=dict)  # passed through to the backend

    def validate(self) -> Config:
        info = get_backend(self.backend).info
        if not self.inputs:
            raise ConfigurationError("At least one input path is required")
        if not self.dry_run and info.requires_api_key and not self.api_key:
            primary, *others = info.api_key_env_vars
            also = f" (or {', '.join(others)})" if others else ""
            where = f" Get a key at {info.api_key_url}" if info.api_key_url else ""
            raise ConfigurationError(f"No API key found. Set {primary}{also}, or pass --api-key.{where}")
        if self.output_format not in OUTPUT_EXTENSIONS:
            raise ConfigurationError(f"Unsupported output format: {self.output_format}")
        if self.output_format not in info.output_formats:
            raise ConfigurationError(f"The {info.label} backend cannot produce {self.output_format} output")
        if self.mode is not None and self.mode not in info.modes:
            choices = f" (choose from {', '.join(info.modes)})" if info.modes else ""
            raise ConfigurationError(f"Unsupported mode for {info.label}: {self.mode}{choices}")
        if self.model is not None and info.default_model is None:
            raise ConfigurationError(f"The {info.label} backend does not take --model")
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
