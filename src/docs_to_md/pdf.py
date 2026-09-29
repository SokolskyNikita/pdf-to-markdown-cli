"""Local PDF page selection and splitting."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from docs_to_md.errors import ConfigurationError, PDFProcessingError

_RANGE_PART = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


@dataclass(frozen=True)
class PdfChunk:
    """A slice of a source document submitted as one API request."""

    path: Path
    pages: Sequence[int]  # 0-based page numbers in the source document

    @property
    def first_page(self) -> int:
        return self.pages[0] if self.pages else 0


def validate_page_range(spec: str) -> str:
    """Check ``spec`` syntax (e.g. ``"0,5-10"``) and return it normalized."""
    parts = [p for p in spec.split(",") if p.strip()]
    if not parts:
        raise ConfigurationError(f"Invalid page range: {spec!r}")
    for part in parts:
        match = _RANGE_PART.match(part)
        if not match:
            raise ConfigurationError(
                f"Invalid page range {spec!r}: expected comma-separated pages or ranges like '0,5-10'"
            )
        start, end = match.group(1), match.group(2)
        if end is not None and int(end) < int(start):
            raise ConfigurationError(f"Invalid page range {spec!r}: {part.strip()} is reversed")
    return ",".join(p.strip().replace(" ", "") for p in parts)


def select_pages(total_pages: int, page_range: str | None = None, max_pages: int | None = None) -> list[int]:
    """Resolve the 0-based pages to convert, mirroring the API semantics.

    ``page_range`` takes precedence over ``max_pages``. Pages past the end of the
    document are ignored.
    """
    if page_range:
        selected = set()
        for part in validate_page_range(page_range).split(","):
            start, _, end = part.partition("-")
            selected.update(range(int(start), int(end or start) + 1))
        pages = sorted(p for p in selected if p < total_pages)
    else:
        pages = list(range(total_pages))
    if max_pages is not None:
        pages = pages[:max_pages]
    return pages


def count_pages(path: Path) -> int:
    try:
        with pikepdf.open(path) as pdf:
            return len(pdf.pages)
    except pikepdf.PdfError as e:
        raise PDFProcessingError(f"Cannot read PDF {path.name}: {e}") from e


def split_pdf(
    path: Path,
    out_dir: Path,
    chunk_size: int | None,
    page_range: str | None = None,
    max_pages: int | None = None,
) -> list[PdfChunk]:
    """Split ``path`` into chunks of at most ``chunk_size`` selected pages.

    When every page is selected and fits in a single chunk, the original file is
    returned as-is instead of being rewritten.
    """
    try:
        with pikepdf.open(path) as pdf:
            total = len(pdf.pages)
            pages = select_pages(total, page_range, max_pages)
            if not pages:
                raise PDFProcessingError(f"{path.name} has {total} page(s); none match the requested pages")
            size = chunk_size or len(pages)
            if len(pages) == total and total <= size:
                return [PdfChunk(path=path, pages=pages)]

            groups = [pages[i : i + size] for i in range(0, len(pages), size)]
            chunks: list[PdfChunk] = []
            for index, group in enumerate(groups):
                chunk_path = out_dir / f"{index + 1:04d}of{len(groups):04d}.pdf"
                with pikepdf.new() as chunk_pdf:
                    for page in group:
                        chunk_pdf.pages.append(pdf.pages[page])
                    chunk_pdf.save(chunk_path)
                chunks.append(PdfChunk(path=chunk_path, pages=group))
            return chunks
    except pikepdf.PdfError as e:
        raise PDFProcessingError(f"Cannot read PDF {path.name}: {e}") from e
    except OSError as e:
        raise PDFProcessingError(f"Cannot split PDF {path.name}: {e}") from e
