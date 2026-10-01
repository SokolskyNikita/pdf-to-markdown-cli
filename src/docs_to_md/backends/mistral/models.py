"""Mistral OCR request building, response parsing, and pricing.

References:
- https://docs.mistral.ai/capabilities/document_ai/basic_ocr
- https://docs.mistral.ai/api/endpoint/ocr
- https://mistral.ai/pricing
"""

from __future__ import annotations

import base64
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docs_to_md.backends.base import parse_option_value
from docs_to_md.errors import APIError
from docs_to_md.pdf import select_pages

# OCR 4.0 read our samples best: OCR 4.1 (mistral-ocr-latest) dropped a table
# row and writes math as \( \) instead of $.
DEFAULT_MODEL = "mistral-ocr-4-0"
OUTPUT_FORMATS = frozenset({"markdown"})

# Input extension (without dot) -> MIME type. Images are sent as image_url,
# everything else as document_url. HTML, RTF, and plain text are accepted by the
# API but come back as unconverted source, so they aren't listed.
IMAGE_MIME_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "bmp": "image/bmp",
    "avif": "image/avif",
    "heic": "image/heic",
}
DOCUMENT_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}
INPUT_MIME_TYPES: dict[str, str] = {**DOCUMENT_MIME_TYPES, **IMAGE_MIME_TYPES}

# US dollars per 1,000 pages, by model name and alias.
PRICES: dict[str, float] = {
    **dict.fromkeys(("mistral-ocr-4-0", "mistral-ocr-4-1", "mistral-ocr-4", "mistral-ocr-latest"), 4.0),
    **dict.fromkeys(("mistral-ocr-2512", "mistral-ocr-3", "mistral-ocr-3-0"), 2.0),
}
# OCR 3 misplaces body text when headers and footers are split out (all of a
# Chinese page went to the header), so it keeps them in the text.
KEEPS_HEADERS = frozenset(name for name, price in PRICES.items() if price < 4.0)

_DATA_URL = re.compile(r"^data:[^,]*;base64,")
# A footer line that is only a page number, e.g. "12", "- 12 -", "[xiv]".
_PAGE_NUMBER = re.compile(r"^[\s\-–—.()\[\]|]*(?:\d{1,4}|[ivxlcdm]{1,8})[\s\-–—.()\[\]|]*$", re.IGNORECASE)
# A footer line that starts with a footnote marker: "1 Cf.", "¹", "*", "<sup>1</sup>", "$^{1}$".
_FOOTNOTE_START = re.compile(r"^\s*(?:\d|[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§]|<sup>|\$\^|\[\^)")
# A header line that is a footnote: "$^{1}$ Cf.", "(1) Cf.", "14. La". Running
# heads often start with a bare page number, so that doesn't count here.
_HEADER_FOOTNOTE = re.compile(
    r"^\s*(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+|<sup>[^<]*</sup>|\$\^\{?[^$]*\}?\$|\[\^[^\]]*\]|\(\d{1,3}\)|\d{1,3}\.(?=\s))\s*\S"
)


def requested_pages(page_range: str | None, max_pages: int | None) -> list[int] | None:
    """0-based pages to ask for when a document is sent whole, or None for all.

    The API ignores pages past the end, so no page count is needed.
    """
    if page_range is None and max_pages is None:
        return None
    last = max(int(n) for n in re.findall(r"\d+", page_range)) if page_range else max_pages - 1
    return select_pages(last + 1, page_range, max_pages)


@dataclass
class OCRRequest:
    """Everything needed to build one /ocr request body."""

    model: str
    include_images: bool = True
    pages: list[int] | None = None
    extra: dict[str, str] | None = None

    def body(self, path: Path) -> dict[str, Any]:
        extension = path.suffix.lower().lstrip(".")
        mime_type = INPUT_MIME_TYPES.get(extension)
        if not mime_type:
            raise APIError(f"Unsupported file type: {path.name}")
        data_url = f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode()}"
        kind = "image_url" if extension in IMAGE_MIME_TYPES else "document_url"
        body: dict[str, Any] = {
            "model": self.model,
            "document": {"type": kind, kind: data_url},
            "include_image_base64": self.include_images,
        }
        if self.model not in KEEPS_HEADERS:
            # Running headers, footers, and page numbers go to separate fields.
            # Footnotes land there too, so parse_response adds them back.
            body.update(extract_header=True, extract_footer=True)
        if self.pages is not None and kind == "document_url":
            body["pages"] = self.pages
        body.update({key: parse_option_value(value) for key, value in (self.extra or {}).items()})
        return body


@dataclass
class OCRResult:
    pages: list[str]  # Markdown per page
    indexes: list[int]  # 0-based page of the sent document for each entry in pages
    images: dict[str, str] = field(default_factory=dict)  # name -> base64
    pages_processed: int = 0
    cost_cents: float | None = None


def cost_cents(model: str, pages: int) -> float | None:
    """What ``pages`` pages cost, or None for models without a known price."""
    price = PRICES.get(model)
    return None if price is None else pages * price / 10  # $/1k pages -> cents per page


def _link(name: str) -> re.Pattern[str]:
    """A Markdown link or image whose target is ``name``, e.g. ``![img-0.jpeg](img-0.jpeg)``."""
    return re.compile(rf"!?\[[^\]\n]*\]\({re.escape(name)}\)")


def _footer_key(line: str) -> str:
    """``line`` with numbers blanked, so running footers match across pages."""
    return re.sub(r"\d+", "#", " ".join(line.split()).lower())


def _notes(pages: list[dict[str, Any]]) -> list[str]:
    """The footnotes Mistral split out of each page's text.

    With header and footer extraction on, OCR 4.x puts footnotes in the footer
    along with the page number, so the footer is kept minus page numbers and
    running footers (lines that repeat on another page and aren't footnotes).
    On a scan of two facing pages, the left page's footnotes can land in the
    header instead, between the running heads.
    """
    footers = [str(page.get("footer") or "").splitlines() for page in pages]
    seen = Counter(key for lines in footers for key in {_footer_key(line) for line in lines if line.strip()})

    def dropped(line: str) -> bool:
        if not line.strip():
            return False
        if _PAGE_NUMBER.match(line):
            return True
        return seen[_footer_key(line)] > 1 and not _FOOTNOTE_START.match(line)

    notes = []
    for page, lines in zip(pages, footers, strict=True):
        header = [line for line in str(page.get("header") or "").splitlines() if _HEADER_FOOTNOTE.match(line)]
        text = "\n".join([*header, *(line for line in lines if not dropped(line))])
        notes.append(re.sub(r"\n{3,}", "\n\n", text).strip())
    return notes


def _page_markdown(page: dict[str, Any], notes: str, include_images: bool, images: dict[str, str]) -> str:
    text = str(page.get("markdown") or "")
    if notes:
        text = f"{text.rstrip()}\n\n{notes}" if text.strip() else notes
    # With --api-option table_format=..., tables come separately behind [tbl-0.md](tbl-0.md).
    for table in page.get("tables") or []:
        name, content = str(table.get("id") or ""), str(table.get("content") or "")
        if name:
            text = _link(name).sub(lambda _, content=content: content.strip(), text)
    for image in page.get("images") or []:
        name = str(image.get("id") or "")
        data = image.get("image_base64")
        if not name:
            continue
        if not include_images or not data:
            text = re.sub(r"\n{3,}", "\n\n", _link(name).sub("", text))
            continue
        unique = name if name not in images else f"page{page.get('index', 0)}_{name}"
        if unique != name:
            text = _link(name).sub(f"![{unique}]({unique})", text)
        images[unique] = _DATA_URL.sub("", str(data))
    return text


def parse_response(data: dict[str, Any], requested_model: str, include_images: bool) -> OCRResult:
    """Extract per-page Markdown and images from an /ocr payload, or raise ``APIError``."""
    pages = data.get("pages")
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        raise APIError("the API returned malformed output (no pages)")
    if not pages:
        raise APIError("the API returned no pages")
    pages = sorted(pages, key=lambda page: int(page.get("index") or 0))
    images: dict[str, str] = {}
    notes = _notes(pages)
    texts = [
        _page_markdown(page, note, include_images, images) for page, note in zip(pages, notes, strict=True)
    ]
    usage = data.get("usage_info") or {}
    processed = int(usage.get("pages_processed") or len(pages))
    return OCRResult(
        pages=texts,
        indexes=[int(page.get("index") or 0) for page in pages],
        images=images,
        pages_processed=processed,
        cost_cents=cost_cents(str(data.get("model") or requested_model), processed),
    )
