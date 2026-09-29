import base64
import json

import pytest

from docs_to_md.assemble import ChunkOutput, Document, assemble, write_document
from docs_to_md.errors import ResultProcessingError

from .conftest import PNG_B64, PNG_BYTES

MARKER = "-" * 48


def test_markdown_rewrites_image_links_with_url_encoding():
    doc = assemble(
        [ChunkOutput(pages=[0], content="![a](fig.png)\n", images={"fig.png": PNG_B64})],
        "markdown",
        "my report_images",
    )
    assert doc.text == "![a](my%20report_images/fig.png)\n"
    assert doc.images == {"fig.png": PNG_BYTES}


def test_markdown_chunks_are_joined_and_pages_renumbered():
    chunks = [
        ChunkOutput(pages=[0, 1], content=f"{{0}}{MARKER}\n\nA\n\n{{1}}{MARKER}\n\nB\n"),
        ChunkOutput(pages=[5, 9], content=f"\n{{0}}{MARKER}\n\nC\n\n{{1}}{MARKER}\n\nD\n"),
    ]
    text = assemble(chunks, "markdown", "x_images").text
    assert [line.split("}")[0] for line in text.splitlines() if line.endswith(MARKER)] == [
        "{0",
        "{1",
        "{5",
        "{9",
    ]
    assert "B\n\n{5}" in text


def test_image_names_colliding_across_chunks_are_made_unique():
    chunks = [
        ChunkOutput(pages=[0], content="![](img.png)", images={"img.png": PNG_B64}),
        ChunkOutput(pages=[1], content="![](img.png)", images={"img.png": PNG_B64}),
    ]
    doc = assemble(chunks, "markdown", "d_images")
    assert sorted(doc.images) == ["chunk2_img.png", "img.png"]
    assert "](d_images/img.png)" in doc.text
    assert "](d_images/chunk2_img.png)" in doc.text


def test_image_names_are_stripped_of_directories():
    doc = assemble(
        [ChunkOutput(pages=[0], content="![](../x.png)", images={"../x.png": PNG_B64})],
        "markdown",
        "d_images",
    )
    assert list(doc.images) == ["x.png"]


def test_undecodable_image_is_skipped():
    doc = assemble(
        [ChunkOutput(pages=[0], content="![](bad.png)", images={"bad.png": "!!!notbase64"})],
        "markdown",
        "d_images",
    )
    assert doc.images == {}
    assert doc.text == "![](bad.png)\n"


def test_markdown_reflow_can_be_disabled():
    long_a = "This is a long paragraph line that was wrapped by OCR output even though"
    long_b = "it should stay as one paragraph because the sentence continues naturally."
    content = f"{long_a}\n{long_b}\n"
    reflowed = assemble([ChunkOutput(pages=[0], content=content)], "markdown", "d")
    kept = assemble([ChunkOutput(pages=[0], content=content)], "markdown", "d", reflow_markdown=False)
    assert reflowed.text == f"{long_a} {long_b}\n"
    assert kept.text == content


def test_html_single_chunk_is_kept_intact():
    html = '<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body><img src="a.png"/></body></html>'
    doc = assemble([ChunkOutput(pages=[0], content=html, images={"a.png": PNG_B64})], "html", "d_images")
    assert doc.text == html.replace('src="a.png"', 'src="d_images/a.png"')


def test_html_chunks_merge_bodies_and_renumber_pages():
    def page(n, text):
        return (
            f'<html><head><title>t</title></head><body><div class="page" data-page-id="{n}">'
            f"{text}</div></body></html>"
        )

    chunks = [
        ChunkOutput(pages=[0], content=page(0, "one")),
        ChunkOutput(pages=[1], content=page(0, "two")),
    ]
    text = assemble(chunks, "html", "d").text
    assert text.count("<body>") == 1
    assert text.count("<title>t</title>") == 1
    assert 'data-page-id="0">one' in text
    assert 'data-page-id="1">two' in text


def test_json_chunks_merge_children_and_metadata():
    def chunk(pages):
        return ChunkOutput(
            pages=pages,
            content={
                "block_type": "Document",
                "children": [
                    {
                        "id": "/page/0/Page/0",
                        "page": 0,
                        "html": '<img src="p.png"/>',
                        "children": [{"id": "/page/0/Text/1", "page": 0}],
                    }
                ],
                "metadata": {"page_stats": [{"page_id": 0}], "failed_pages": [0], "note": "first"},
            },
            images={"p.png": PNG_B64},
        )

    doc = assemble([chunk([0]), chunk([3])], "json", "d_images")
    data = json.loads(doc.text)
    assert data["block_type"] == "Document"
    assert [c["id"] for c in data["children"]] == ["/page/0/Page/0", "/page/3/Page/0"]
    assert data["children"][1]["children"][0] == {"id": "/page/3/Text/1", "page": 3}
    assert data["children"][0]["html"] == '<img src="d_images/p.png"/>'
    assert data["children"][1]["html"] == '<img src="d_images/chunk2_p.png"/>'
    assert data["metadata"] == {
        "page_stats": [{"page_id": 0}, {"page_id": 3}],
        "failed_pages": [0, 3],
        "note": "first",
    }


def test_page_anchors_and_links_are_renumbered():
    content = '<span id="page-0-1"></span>Intro\n\nSee [above](#page-0-1).\n'
    doc = assemble(
        [ChunkOutput(pages=[0], content=content), ChunkOutput(pages=[7], content=content)],
        "markdown",
        "d",
    )
    assert doc.text.count('id="page-0-1"') == 1
    assert doc.text.count('id="page-7-1"') == 1
    assert "(#page-7-1)" in doc.text


def test_json_content_refs_are_renumbered():
    chunk = ChunkOutput(
        pages=[4],
        content={
            "children": [{"id": "/page/0/Page/0", "html": "<content-ref src='/page/0/Text/1'></content-ref>"}]
        },
    )
    data = json.loads(assemble([chunk], "json", "d").text)
    assert data["children"][0]["html"] == "<content-ref src='/page/4/Text/1'></content-ref>"


def test_non_pdf_chunk_without_page_list_keeps_numbers():
    doc = assemble([ChunkOutput(pages=(), content=f"{{2}}{MARKER}\n")], "markdown", "d")
    assert doc.text.startswith("{2}")


def test_missing_content_is_an_error():
    with pytest.raises(ResultProcessingError, match="no html content"):
        assemble([ChunkOutput(pages=[0], content=None)], "html", "d")


def test_no_chunks_is_an_error():
    with pytest.raises(ResultProcessingError):
        assemble([], "markdown", "d")


def test_write_document_creates_images_only_when_present(tmp_path):
    out, images = tmp_path / "a.md", tmp_path / "a_images"
    write_document(Document(text="# hi\n", images={}), out, images)
    assert out.read_text() == "# hi\n"
    assert not images.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_write_document_replaces_previous_output_and_images(tmp_path):
    out, images = tmp_path / "sub" / "a.md", tmp_path / "sub" / "a_images"
    write_document(Document(text="old", images={"old.png": b"1"}), out, images)
    write_document(Document(text="new", images={"new.png": base64.b64decode(PNG_B64)}), out, images)
    assert out.read_text() == "new"
    assert [p.name for p in images.iterdir()] == ["new.png"]
    assert sorted(p.name for p in out.parent.iterdir()) == ["a.md", "a_images"]


def test_write_document_uses_unix_newlines(tmp_path):
    out = tmp_path / "a.md"
    write_document(Document(text="one\ntwo\n", images={}), out, tmp_path / "a_images")
    assert out.read_bytes() == b"one\ntwo\n"
