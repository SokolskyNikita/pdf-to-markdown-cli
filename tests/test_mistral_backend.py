"""MistralBackend: request bodies, response parsing, page handling, and cost.

These run through the real pipeline with ``FakeOCR`` standing in for the HTTP
client, which is tested on its own in ``test_mistral_client.py``.
"""

from __future__ import annotations

import base64
import re
import threading

import pytest

from docs_to_md.backends import get_backend
from docs_to_md.backends.mistral import MistralBackend
from docs_to_md.backends.mistral.client import MistralClient
from docs_to_md.backends.mistral.models import (
    OCRRequest,
    cost_cents,
    parse_response,
    requested_pages,
)
from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import APIError, ConfigurationError, FatalAPIError
from docs_to_md.pipeline import Pipeline

from .conftest import PNG_B64, PNG_BYTES

MARKER = re.compile(r"^\{(\d+)\}-{48}$", re.MULTILINE)


def page(index, markdown, images=(), tables=()):
    return {"index": index, "markdown": markdown, "images": list(images), "tables": list(tables)}


def image(name, data=f"data:image/png;base64,{PNG_B64}"):
    return {"id": name, "image_base64": data}


def payload(pages, model="mistral-ocr-4-0", processed=None):
    return {
        "pages": pages,
        "model": model,
        "usage_info": {"pages_processed": len(pages) if processed is None else processed},
    }


def page_count(body):
    """How many pages the PDF in ``body`` has, by counting page objects."""
    data = base64.b64decode(body["document"]["document_url"].split(",", 1)[1])
    return len(re.findall(rb"/Type\s*/Page\b", data))


class FakeOCR:
    """Stand-in for MistralClient: answers each request with ``responder(body, index)``."""

    def __init__(self, responder=None):
        self.bodies: list = []
        self._lock = threading.Lock()
        self.responder = responder or self.echo_pages

    @staticmethod
    def echo_pages(body, index):
        document = body["document"]
        if document["type"] == "image_url":
            return payload([page(0, "image text")])
        pages = body.get("pages") or range(page_count(body))
        return payload([page(i, f"page {i} of request {index}") for i in pages])

    def ocr(self, body, what):
        with self._lock:
            index = len(self.bodies)
            self.bodies.append(body)
        result = self.responder(body, index)
        if isinstance(result, Exception):
            raise result
        return result


def run(inputs, console, client=None, **overrides):
    config = Config(inputs=list(inputs), backend="mistral", api_key="k", **overrides).validate()
    client = client or FakeOCR()
    jobs = plan_jobs(
        config.inputs,
        config.output_format,
        config.output_dir,
        input_extensions=MistralBackend.info.input_extensions,
    )
    return Pipeline(config, console, backend=MistralBackend(config, client)).run(jobs), client


# -- registration and config ------------------------------------------------


def test_info_describes_the_ocr_api():
    info = get_backend("mistral").info
    assert info is MistralBackend.info
    assert {"pdf", "docx", "pptx", "xlsx", "png", "avif", "heic"} <= info.input_extensions
    assert not {"html", "txt", "rtf"} & info.input_extensions  # returned unconverted
    assert info.output_formats == {"markdown"}
    assert info.modes == ()
    assert (info.max_upload_bytes, info.chunk_size) == (50 * 1024 * 1024, 25)
    assert (info.default_model, info.api_key_env_vars) == ("mistral-ocr-4-0", ("MISTRAL_API_KEY",))


def test_config_is_checked_against_the_backend(tmp_path):
    with pytest.raises(ConfigurationError, match="Mistral backend cannot produce html"):
        Config(inputs=[tmp_path], backend="mistral", api_key="k", output_format="html").validate()
    with pytest.raises(ConfigurationError, match="Unsupported mode for Mistral"):
        Config(inputs=[tmp_path], backend="mistral", api_key="k", mode="accurate").validate()
    with pytest.raises(ConfigurationError, match="MISTRAL_API_KEY"):
        Config(inputs=[tmp_path], backend="mistral").validate()


def test_from_config_builds_a_client(tmp_path):
    config = Config(inputs=[tmp_path], backend="mistral", api_key="k", timeout=30).validate()
    built = MistralBackend.from_config(config, threading.Event())
    assert isinstance(built.client, MistralClient)
    assert (built.client.base_url, built.client.label, built.client.timeout) == (
        "https://api.mistral.ai/v1",
        "Mistral",
        30,
    )


# -- requests ------------------------------------------------------------------


def test_pdf_chunks_are_sent_as_documents(examples, console):
    summary, client = run([examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=2)
    assert summary.exit_code == 0
    first, _ = client.bodies
    document = first["document"]
    assert document["type"] == "document_url"
    assert document["document_url"].startswith("data:application/pdf;base64,")
    assert (first["model"], first["include_image_base64"]) == ("mistral-ocr-4-0", True)
    assert first["extract_header"] is True and first["extract_footer"] is True
    assert "pages" not in first  # the split PDF holds only the selected pages
    assert sorted(page_count(body) for body in client.bodies) == [1, 2]


def test_images_are_sent_as_images(tmp_path, console):
    (tmp_path / "scan.png").write_bytes(PNG_BYTES)
    (tmp_path / "photo.heic").write_bytes(b"heic")
    summary, client = run([tmp_path], console, page_range="3")
    assert summary.exit_code == 0
    kinds = sorted(body["document"]["type"] for body in client.bodies)
    assert kinds == ["image_url", "image_url"]
    urls = sorted(body["document"]["image_url"] for body in client.bodies)
    assert urls[0].startswith("data:image/heic;base64,")
    assert urls[1] == f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode()}"
    assert all("pages" not in body for body in client.bodies)  # an image is one page
    assert (tmp_path / "scan.md").read_text() == "image text\n"


def test_whole_documents_get_page_selection(tmp_path, console):
    (tmp_path / "notes.docx").write_bytes(b"docx")
    (tmp_path / "sheet.xlsx").write_bytes(b"xlsx")
    summary, client = run([tmp_path], console, page_range="1,3-4", max_pages=2, paginate=True)
    assert summary.exit_code == 0
    assert all(body["pages"] == [1, 3] for body in client.bodies)
    urls = sorted(body["document"]["document_url"].split(";")[0] for body in client.bodies)
    assert urls == [
        "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "data:application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    # Page markers keep the API's page numbers.
    assert MARKER.findall((tmp_path / "notes.md").read_text()) == ["1", "3"]


def test_requested_pages():
    assert requested_pages(None, None) is None
    assert requested_pages(None, 3) == [0, 1, 2]
    assert requested_pages("5,0-1", None) == [0, 1, 5]
    assert requested_pages("5,0-1", 2) == [0, 1]


def test_options_shape_the_request(examples, console):
    _, client = run(
        [examples / "equations.pdf"],
        console,
        model="mistral-ocr-latest",
        disable_image_extraction=True,
        extra_options={"table_format": "html", "extract_footer": "false", "image_limit": "3"},
    )
    (body,) = client.bodies
    assert body["model"] == "mistral-ocr-latest"
    assert body["include_image_base64"] is False
    assert (body["table_format"], body["image_limit"]) == ("html", 3)  # JSON values are decoded
    assert (body["extract_header"], body["extract_footer"]) == (True, False)  # and override defaults


def test_ocr_3_keeps_headers_in_the_text(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF")
    for model in ("mistral-ocr-2512", "mistral-ocr-3"):
        assert "extract_header" not in OCRRequest(model).body(path)


def test_unsupported_file_types_are_rejected_locally(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"x")
    with pytest.raises(APIError, match="Unsupported file type"):
        OCRRequest("mistral-ocr-4-0").body(path)


# -- responses -----------------------------------------------------------------


def test_split_pdfs_merge_with_source_page_numbers(examples, console):
    summary, _ = run([examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=1, paginate=True)
    assert summary.exit_code == 0
    text = (examples / "alice_in_wonderland_sample.md").read_text()
    assert [int(n) for n in MARKER.findall(text)] == [0, 1, 2]
    assert "3 pages" in console.err


def test_images_are_saved_and_linked(examples, console):
    def responder(body, index):
        return payload(
            [
                page(0, "Text\n\n![img-0.jpeg](img-0.jpeg)", [image("img-0.jpeg")]),
                page(1, "![img-0.jpeg](img-0.jpeg)\n\nMore", [image("img-0.jpeg")]),
            ]
        )

    summary, _ = run([examples / "alice_in_wonderland_sample.pdf"], console, FakeOCR(responder))
    assert summary.exit_code == 0
    text = (examples / "alice_in_wonderland_sample.md").read_text()
    assert "![img-0.jpeg](alice_in_wonderland_sample_images/img-0.jpeg)" in text
    # A repeated name on another page gets its own file.
    assert "![page1_img-0.jpeg](alice_in_wonderland_sample_images/page1_img-0.jpeg)" in text
    images = examples / "alice_in_wonderland_sample_images"
    assert sorted(p.name for p in images.iterdir()) == ["img-0.jpeg", "page1_img-0.jpeg"]
    assert (images / "img-0.jpeg").read_bytes() == PNG_BYTES


def test_image_links_are_dropped_without_images(examples, console):
    def responder(body, index):
        return payload([page(0, "Before\n\n![img-0.jpeg](img-0.jpeg)\n\nAfter", [image("img-0.jpeg", None)])])

    summary, _ = run([examples / "equations.pdf"], console, FakeOCR(responder), disable_image_extraction=True)
    assert summary.exit_code == 0
    assert (examples / "equations.md").read_text() == "Before\n\nAfter\n"
    assert not (examples / "equations_images").exists()


def test_separate_tables_are_put_back_inline():
    table = {"id": "tbl-0.html", "content": "<table><tr><td>\\alpha</td></tr></table>", "format": "html"}
    result = parse_response(
        payload([page(0, "# Title\n\n[tbl-0.html](tbl-0.html)\n\nNote", tables=[table])]),
        "mistral-ocr-4-0",
        include_images=True,
    )
    assert result.pages == ["# Title\n\n<table><tr><td>\\alpha</td></tr></table>\n\nNote"]


def test_pages_are_ordered_by_index():
    result = parse_response(payload([page(4, "b"), page(2, "a")]), "mistral-ocr-4-0", include_images=True)
    assert (result.pages, result.indexes) == (["a", "b"], [2, 4])


@pytest.mark.parametrize(
    ("data", "message"),
    [({"model": "x"}, "malformed"), ({"pages": ["x"]}, "malformed"), (payload([]), "no pages")],
)
def test_bad_responses_are_errors(data, message):
    with pytest.raises(APIError, match=message):
        parse_response(data, "mistral-ocr-4-0", include_images=True)


def test_cost_is_reported(examples, console):
    summary, _ = run([examples / "alice_in_wonderland_sample.pdf"], console)
    assert summary.cost_cents == pytest.approx(1.2)  # 3 pages at $4 per 1,000
    assert "3 pages, $0.01)" in console.err


def test_cost_cents():
    assert cost_cents("mistral-ocr-4-0", 1000) == pytest.approx(400)
    assert cost_cents("mistral-ocr-latest", 10) == pytest.approx(4)
    assert cost_cents("mistral-ocr-2512", 10) == pytest.approx(2)
    assert cost_cents("some-other-model", 10) is None


def test_billed_model_sets_the_price():
    result = parse_response(payload([page(0, "a")], model="mistral-ocr-2512", processed=5), "x", True)
    assert (result.pages_processed, result.cost_cents) == (5, pytest.approx(1.0))


def test_fatal_errors_stop_the_run(examples, console):
    with pytest.raises(FatalAPIError):
        run([examples], console, FakeOCR(lambda body, i: FatalAPIError("bad key")))


def test_file_errors_fail_only_that_file(examples, console):
    def responder(body, index):
        if page_count(body) == 1:
            return APIError("OCR of equations.pdf: HTTP 400: Document type not supported")
        return FakeOCR.echo_pages(body, index)

    summary, _ = run([examples], console, FakeOCR(responder))
    assert summary.exit_code == 1
    assert (summary.count("failed"), summary.count("converted")) == (1, 1)
    assert "Document type not supported" in console.err
