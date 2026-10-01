"""Cutting two-page scans in half for --split-spreads."""

from __future__ import annotations

import pikepdf

from docs_to_md.pdf import Chunk
from docs_to_md.spreads import join_halves, split_spreads, spread_halves


def spread_pdf(path, *sizes):
    """A PDF with blank pages of the given (width, height) sizes."""
    with pikepdf.new() as pdf:
        for size in sizes:
            pdf.add_blank_page(page_size=size)
        pdf.save(path)
    return path


def test_split_spreads_cuts_landscape_pages_in_half(tmp_path):
    source = spread_pdf(tmp_path / "scan.pdf", (1000, 700), (500, 700), (800, 700))
    counts = split_spreads(source, tmp_path / "halves.pdf")
    assert counts == [2, 1, 1]  # 800 x 700 isn't wide enough for a spread
    with pikepdf.open(tmp_path / "halves.pdf") as pdf:
        boxes = [[float(v) for v in page.mediabox] for page in pdf.pages]
    assert boxes == [[0, 0, 500, 700], [500, 0, 1000, 700], [0, 0, 500, 700], [0, 0, 800, 700]]


def test_split_spreads_leaves_rotated_pages_whole(tmp_path):
    source = spread_pdf(tmp_path / "scan.pdf", (1000, 700))
    with pikepdf.open(source, allow_overwriting_input=True) as pdf:
        pdf.pages[0].obj.Rotate = 90
        pdf.save(source)
    assert split_spreads(source, tmp_path / "halves.pdf") == [1]


def test_split_spreads_drops_the_ocr_text_layer(tmp_path):
    # Cropping doesn't crop the text layer, so each half would carry the whole
    # spread's OCR text. Invisible text goes, including inside form XObjects;
    # visible text stays.
    with pikepdf.new() as pdf:
        pdf.add_blank_page(page_size=(1000, 700))
        page = pdf.pages[0]
        form = pdf.make_stream(
            b"BT 3 Tr (form ocr) Tj ET", Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form
        )
        form.BBox = [0, 0, 1000, 700]
        page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm0=form))
        page.obj.Contents = pdf.make_stream(
            b"q 3 Tr BT (ocr) Tj T* (more) ' ET Q BT (printed) Tj ET q /Fm0 Do Q"
        )
        pdf.save(tmp_path / "scan.pdf")
    assert split_spreads(tmp_path / "scan.pdf", tmp_path / "halves.pdf") == [2]

    def shown(stream_owner):
        return [
            bytes(operand)
            for instruction in pikepdf.parse_content_stream(stream_owner)
            for operand in instruction.operands
            if isinstance(operand, pikepdf.String)
        ]

    with pikepdf.open(tmp_path / "halves.pdf") as pdf:
        for half in pdf.pages:
            assert shown(half) == [b"printed"]
            assert shown(half.resources.XObject.Fm0) == []


def test_spread_halves_numbers_the_halves_and_join_halves_regroups_them(tmp_path):
    source = spread_pdf(tmp_path / "scan.pdf", (1000, 700), (500, 700))
    with spread_halves(Chunk(source, pages=(4, 5))) as (halves, counts):
        assert (list(halves.pages), counts) == ([0, 1, 2], [2, 1])
        assert halves.path.name == "scan.pdf" and halves.path.exists()
    assert not halves.path.exists()  # temporary
    assert join_halves(["left\n", " ", "right", "single"], [3, 1]) == ["left\n\nright", "single"]
