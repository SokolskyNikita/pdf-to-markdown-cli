"""The contract between the pipeline and a conversion backend.

The pipeline plans outputs, splits PDFs, schedules chunks on worker threads,
merges the results, and writes files. A backend only turns one chunk into
Markdown, HTML, or JSON.
"""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from docs_to_md.assemble import ChunkOutput
from docs_to_md.pdf import Chunk

if TYPE_CHECKING:
    from docs_to_md.config import Config

CancelCheck = Callable[[], None]
"""Raises ``Cancelled`` once the run is interrupted or another chunk of the file failed."""


def parse_option_value(value: str) -> Any:
    """Decode an ``--api-option`` value for a JSON API: JSON if it parses, else the string."""
    try:
        return json.loads(value)
    except ValueError:
        return value


@dataclass(frozen=True)
class BackendInfo:
    """What a backend accepts, used to validate the config before any work starts."""

    name: str  # the --backend value
    label: str  # human-readable name for messages
    input_extensions: frozenset[str]  # lowercase, without the dot
    output_formats: frozenset[str]  # keys of assemble.OUTPUT_EXTENSIONS
    modes: tuple[str, ...] = ()  # accepted --mode values
    max_upload_bytes: int | None = None  # limit for a document sent whole
    chunk_size: int = 25  # default --chunk-size (PDF pages per request)
    default_model: str | None = None  # None if the backend takes no --model
    api_key_env_vars: tuple[str, ...] = ()  # lookup order; empty if no key is needed
    api_key_url: str | None = None  # where to get a key

    @property
    def requires_api_key(self) -> bool:
        return bool(self.api_key_env_vars)


class Backend(ABC):
    """Converts one chunk at a time.

    ``convert`` runs concurrently on up to ``--concurrency`` worker threads, so
    implementations must be thread-safe. Errors decide how far a failure spreads:

    - ``FatalAPIError`` affects every request (bad key, no credits) and stops the run.
    - ``Cancelled`` comes from ``check_cancelled`` and must be allowed to propagate.
    - Any other ``DocsToMdError`` fails only the file the chunk belongs to.
    """

    info: ClassVar[BackendInfo]

    @classmethod
    @abstractmethod
    def from_config(cls, config: Config, stop_event: threading.Event) -> Backend:
        """Build a backend for a validated ``config``.

        ``stop_event`` is set when the run is interrupted. Long waits should wake
        up on it instead of sleeping through Ctrl-C.
        """

    @abstractmethod
    def convert(self, chunk: Chunk, check_cancelled: CancelCheck) -> ChunkOutput:
        """Convert ``chunk`` to ``config.output_format``, blocking until done.

        Call ``check_cancelled`` between slow steps (uploads, polls, retries) so
        an abandoned chunk stops spending time and credits.
        """
