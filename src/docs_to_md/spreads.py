"""Two-page scans: cut each landscape PDF page into its left and right halves.

Backends that return text per page use this for ``--split-spreads``: they
convert the halves from ``spread_halves`` as separate pages, then
``join_halves`` puts each scan's text back together.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pikepdf

from docs_to_md.errors import PDFProcessingError
from docs_to_md.pdf import Chunk

SPREAD_ASPECT = 1.2  # a page wider than this (width / height) is taken for two facing pages
_SHOW_TEXT = frozenset({"Tj", "TJ", "'", '"'})
_INVISIBLE = 3  # the text render mode of OCR text layers


def _strip_invisible_text(
    pdf: pikepdf.Pdf, owner: pikepdf.Page | pikepdf.Object, resources: pikepdf.Object, mode: int = 0
) -> None:
    """Remove invisible (OCR layer) text from a page or form XObject, and from forms it draws.

    Cropping a page leaves its whole text layer in place, and OpenAI reads it:
    each half of a scan would carry the other half's text. Visible text is kept.
    """
    stack, kept = [], []
    for instruction in pikepdf.parse_content_stream(owner):
        operator = str(instruction.operator)
        if operator == "q":
            stack.append(mode)
        elif operator == "Q":
            mode = stack.pop() if stack else 0
        elif operator == "Tr":
            mode = int(instruction.operands[0])
        elif operator in _SHOW_TEXT and mode == _INVISIBLE:
            if operator not in ("Tj", "TJ"):
                kept.append(
                    pikepdf.ContentStreamInstruction([], pikepdf.Operator("T*"))
                )  # keep the line move
            continue
        elif operator == "Do":
            form = resources.get("/XObject", {}).get(instruction.operands[0])
            if form is not None and form.get("/Subtype") == "/Form":
                _strip_invisible_text(pdf, form, form.get("/Resources", resources), mode)
        kept.append(instruction)
    data = pikepdf.unparse_content_stream(kept)
    if isinstance(owner, pikepdf.Page):
        owner.obj.Contents = pdf.make_stream(data)
    else:
        owner.write(data)


def split_spreads(path: Path, out_path: Path) -> list[int]:
    """Write ``path`` to ``out_path`` with each landscape page cut into its left and right halves.

    Returns how many pages each input page became: 2 for a spread, 1 otherwise.
    Rotated pages are left whole. Split pages lose their invisible OCR text,
    which can't be cut in half with the page.
    """
    try:
        with pikepdf.open(path) as pdf, pikepdf.new() as out:
            counts = []
            for page in pdf.pages:
                x0, y0, x1, y1 = (float(v) for v in page.cropbox)
                rotated = int(page.obj.get("/Rotate", 0)) % 360
                if rotated or abs(x1 - x0) <= SPREAD_ASPECT * abs(y1 - y0):
                    out.pages.append(page)
                    counts.append(1)
                    continue
                _strip_invisible_text(pdf, page, page.resources)
                middle = (x0 + x1) / 2
                for left, right in ((x0, middle), (middle, x1)):
                    out.pages.append(page)  # each append makes a separate copy
                    half = out.pages[-1]
                    for box in ("/CropBox", "/BleedBox", "/TrimBox", "/ArtBox"):
                        if box in half.obj:
                            del half.obj[box]
                    half.mediabox = pikepdf.Array([left, y0, right, y1])
                counts.append(2)
            out.save(out_path)
            return counts
    except pikepdf.PdfError as e:
        raise PDFProcessingError(f"Cannot read PDF {path.name}: {e}") from e
    except OSError as e:
        raise PDFProcessingError(f"Cannot split PDF {path.name}: {e}") from e


@contextmanager
def spread_halves(chunk: Chunk) -> Iterator[tuple[Chunk, list[int]]]:
    """``chunk`` with each two-page scan cut in half, for --split-spreads.

    Yields the new chunk, whose pages are numbered 0..n-1, and how many of its
    pages each page of ``chunk`` became. Combine per-page results with
    ``join_halves``.
    """
    with tempfile.TemporaryDirectory(prefix="pdf-to-md-") as tmp:
        path = Path(tmp) / chunk.path.name
        counts = split_spreads(chunk.path, path)
        yield Chunk(path, pages=tuple(range(sum(counts)))), counts


def join_halves(texts: Sequence[str], counts: Sequence[int]) -> list[str]:
    """Per-page text of the halves from ``spread_halves``, joined back into one string per source page."""
    pages, start = [], 0
    for count in counts:
        pages.append("\n\n".join(text.strip() for text in texts[start : start + count] if text.strip()))
        start += count
    return pages
