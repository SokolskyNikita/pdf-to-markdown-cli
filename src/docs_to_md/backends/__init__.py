"""Conversion backends, selected with ``--backend``.

To add one, subclass ``Backend`` (see ``base.py``) and list it in ``BACKENDS``.
"""

from __future__ import annotations

from docs_to_md.backends.base import Backend, BackendInfo, CancelCheck
from docs_to_md.backends.datalab import DatalabBackend
from docs_to_md.errors import ConfigurationError

DEFAULT_BACKEND = "datalab"

BACKENDS: dict[str, type[Backend]] = {backend.info.name: backend for backend in (DatalabBackend,)}


def get_backend(name: str) -> type[Backend]:
    try:
        return BACKENDS[name]
    except KeyError:
        raise ConfigurationError(f"Unknown backend: {name} (available: {', '.join(BACKENDS)})") from None


__all__ = [
    "BACKENDS",
    "DEFAULT_BACKEND",
    "Backend",
    "BackendInfo",
    "CancelCheck",
    "get_backend",
]
