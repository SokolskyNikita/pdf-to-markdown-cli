#!/usr/bin/env python3
"""Rebuild the benchmark PDFs in ``samples/`` from public-domain Internet Archive scans.

Usage (needs network access, PyMuPDF and Pillow):

    pip install pymupdf pillow
    python benchmarks/scanned_books/build_samples.py

- ``vieira_cartas_pt.pdf``: 8 two-page spreads made by placing consecutive
  pages of the original page scans side by side, without a text layer. Real
  spread scans of suitable books are rare, so this stands in for an open book
  photographed or scanned flat.
- ``multatuli_brieven_nl.pdf`` and ``sevigne_lettres_fr.pdf``: single pages
  from Google's scans, with the Internet Archive's own OCR added as an
  invisible text layer, as in a downloaded "PDF with text".

Page indexes below are 0-based pages of each item's scan (``/page/nN``).
"""

from __future__ import annotations

import io
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"
IA = "https://archive.org/download"

# Padre António Vieira, Cartas, vol. III, ed. J. Lúcio d'Azevedo (Coimbra, 1928).
VIEIRA = "tomo-iii_202302"
VIEIRA_SPREADS = [(55, 56), (59, 60), (257, 258), (447, 448), (483, 484), (557, 558), (613, 614), (739, 740)]
# Multatuli, Brieven, vol. 1 (1891), Google scan of a library copy.
MULTATULI = "brievenvanmulta01multgoog"
MULTATULI_PAGES = [72, 94, 95, 124, 125]
# Lettres de Madame de Sévigné, vol. 6, ed. Monmerqué (Hachette, 1862), Google scan.
SEVIGNE = "lettresdemadame03monmgoog"
SEVIGNE_PAGES = [242, 243, 244]

PAGE_WIDTH_PX = 1200  # per book page in the spreads, about 165 dpi
JPEG_QUALITY = 60


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def build_spreads(path: Path) -> None:
    doc = fitz.open()
    for left, right in VIEIRA_SPREADS:
        images = []
        for n in (left, right):
            image = Image.open(io.BytesIO(fetch(f"{IA}/{VIEIRA}/page/n{n}.jpg"))).convert("L")
            size = (PAGE_WIDTH_PX, round(image.height * PAGE_WIDTH_PX / image.width))
            images.append(image.resize(size, Image.Resampling.LANCZOS))
        height = max(im.height for im in images)
        spread = Image.new("L", (sum(im.width for im in images), height), 255)
        spread.paste(images[0], (0, 0))
        spread.paste(images[1], (images[0].width, 0))
        data = io.BytesIO()
        spread.save(data, "JPEG", quality=JPEG_QUALITY, optimize=True)
        scale = 738 / height  # the book's page height in points
        page = doc.new_page(width=spread.width * scale, height=738)
        page.insert_image(page.rect, stream=data.getvalue())
    doc.save(path, garbage=4, deflate=True)


def ocr_lines(xml: bytes, index: int) -> tuple[int, int, list[tuple[str, tuple[int, int, int, int]]]]:
    """OCR lines and their pixel boxes (left, top, right, bottom) on page ``index`` of a DjVu XML file."""
    page = list(ET.fromstring(xml).iter("OBJECT"))[index]
    lines = []
    for line in page.iter("LINE"):
        words, boxes = [], []
        for word in line.iter("WORD"):
            if word.text and word.text.strip():
                left, bottom, right, top = map(int, word.get("coords").split(",")[:4])
                words.append(word.text.strip())
                boxes.append((left, top, right, bottom))
        if words:
            box = (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            )
            lines.append((" ".join(words), box))
    return int(page.get("width")), int(page.get("height")), lines


def build_with_text_layer(identifier: str, indexes: list[int], path: Path) -> None:
    source = fitz.open(stream=fetch(f"{IA}/{identifier}/{identifier}.pdf"), filetype="pdf")
    xml = fetch(f"{IA}/{identifier}/{identifier}_djvu.xml")
    doc = fitz.open()
    for index in indexes:
        doc.insert_pdf(source, from_page=index, to_page=index)
        page = doc[-1]
        width, height, lines = ocr_lines(xml, index)
        sx, sy = page.rect.width / width, page.rect.height / height
        for text, (left, top, right, bottom) in lines:
            size = max(4.0, (bottom - top) * sy * 0.8)
            box_width = fitz.get_text_length(text, fontname="helv", fontsize=size) or 1
            page.insert_text(
                (left * sx, bottom * sy),
                text,
                fontname="helv",
                fontsize=size,
                render_mode=3,  # invisible, like an OCR text layer
                morph=(fitz.Point(left * sx, bottom * sy), fitz.Matrix((right - left) * sx / box_width, 1)),
            )
    doc.save(path, garbage=4, deflate=True)


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    build_spreads(SAMPLES / "vieira_cartas_pt.pdf")
    build_with_text_layer(MULTATULI, MULTATULI_PAGES, SAMPLES / "multatuli_brieven_nl.pdf")
    build_with_text_layer(SEVIGNE, SEVIGNE_PAGES, SAMPLES / "sevigne_lettres_fr.pdf")
    for pdf in sorted(SAMPLES.glob("*.pdf")):
        print(f"{pdf.name}: {len(fitz.open(pdf))} pages, {pdf.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
