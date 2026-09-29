import pytest

from docs_to_md.errors import ConfigurationError, PDFProcessingError
from docs_to_md.pdf import count_pages, select_pages, split_pdf, validate_page_range


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("0", "0"), (" 0, 5 - 10 ", "0,5-10"), ("3-3", "3-3"), ("1,,2", "1,2")],
)
def test_validate_page_range_normalizes(spec, expected):
    assert validate_page_range(spec) == expected


@pytest.mark.parametrize("spec", ["", "a", "1-", "-3", "5-2", "1.5"])
def test_validate_page_range_rejects_bad_input(spec):
    with pytest.raises(ConfigurationError):
        validate_page_range(spec)


def test_select_pages_defaults_to_all():
    assert select_pages(4) == [0, 1, 2, 3]


def test_select_pages_range_is_sorted_deduplicated_and_clipped():
    assert select_pages(6, "4-9,0,1-2,2") == [0, 1, 2, 4, 5]


def test_select_pages_max_pages_applies_after_range():
    assert select_pages(10, max_pages=3) == [0, 1, 2]
    assert select_pages(10, "5-9", max_pages=2) == [5, 6]


def test_count_pages(examples):
    assert count_pages(examples / "alice_in_wonderland_sample.pdf") == 3


def test_small_pdf_is_not_rewritten(examples, tmp_path):
    source = examples / "alice_in_wonderland_sample.pdf"
    chunks = split_pdf(source, tmp_path, chunk_size=25)
    assert len(chunks) == 1
    assert chunks[0].path == source
    assert list(chunks[0].pages) == [0, 1, 2]


def test_split_into_chunks(examples, tmp_path):
    chunks = split_pdf(examples / "alice_in_wonderland_sample.pdf", tmp_path, chunk_size=2)
    assert [list(c.pages) for c in chunks] == [[0, 1], [2]]
    assert [count_pages(c.path) for c in chunks] == [2, 1]
    assert chunks[1].first_page == 2


def test_page_selection_happens_once_not_per_chunk(examples, tmp_path):
    chunks = split_pdf(examples / "alice_in_wonderland_sample.pdf", tmp_path, chunk_size=1, max_pages=2)
    assert [list(c.pages) for c in chunks] == [[0], [1]]


def test_no_chunk_with_page_range_writes_subset(examples, tmp_path):
    chunks = split_pdf(examples / "alice_in_wonderland_sample.pdf", tmp_path, None, page_range="0,2")
    assert len(chunks) == 1
    assert list(chunks[0].pages) == [0, 2]
    assert count_pages(chunks[0].path) == 2


def test_range_outside_document_fails(examples, tmp_path):
    with pytest.raises(PDFProcessingError, match="none match"):
        split_pdf(examples / "equations.pdf", tmp_path, 25, page_range="5-9")


def test_invalid_pdf_fails(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(PDFProcessingError, match=r"bad\.pdf"):
        split_pdf(bad, tmp_path, 25)
    with pytest.raises(PDFProcessingError):
        count_pages(bad)
