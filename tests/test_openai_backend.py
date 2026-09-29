"""OpenAIBackend and OpenRouterBackend: request bodies, page handling, and cost.

These run through the real pipeline with ``FakeResponses`` standing in for the
HTTP client, which is tested on its own in ``test_openai_client.py``.
"""

from __future__ import annotations

import base64
import json
import re
import threading

import pytest

from docs_to_md.assemble import join_pages
from docs_to_md.backends import BACKENDS, get_backend
from docs_to_md.backends.openai import OpenAIBackend, OpenRouterBackend
from docs_to_md.backends.openai.client import OpenAIClient
from docs_to_md.backends.openai.models import (
    TranscribeRequest,
    cost_cents,
    instructions_for,
    parse_response,
)
from docs_to_md.config import Config
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import APIError, ConfigurationError, FatalAPIError
from docs_to_md.pdf import Chunk
from docs_to_md.pipeline import Pipeline

from .conftest import PNG_BYTES

MARKER = re.compile(r"^\{(\d+)\}-{48}$", re.MULTILINE)


def payload(pages, model="gpt-6-luna", usage=None, status="completed", **extra):
    """A /responses payload whose message carries ``pages`` as the structured output."""
    return {
        "status": status,
        "model": model,
        "service_tier": "default",
        "output": [
            {"type": "reasoning", "content": []},
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"pages": pages})}]},
        ],
        "usage": usage or {"input_tokens": 1_000_000, "output_tokens": 0},
        **extra,
    }


class FakeResponses:
    """Stand-in for OpenAIClient: answers each request with ``responder(body, index)``."""

    def __init__(self, responder=None):
        self.bodies: list = []
        self._lock = threading.Lock()
        self.responder = responder or self.echo_pages

    @staticmethod
    def echo_pages(body, index):
        count = int(re.search(r"(\d+) pages?", body["instructions"]).group(1))
        name = body["input"][0]["content"][0].get("filename", "image")
        return payload([f"{name} page {i}" for i in range(count)])

    def create_response(self, body, what):
        with self._lock:
            index = len(self.bodies)
            self.bodies.append(body)
        result = self.responder(body, index)
        if isinstance(result, Exception):
            raise result
        return result


def run(inputs, console, client=None, backend=OpenAIBackend, **overrides):
    config = Config(inputs=list(inputs), backend=backend.info.name, api_key="k", **overrides).validate()
    client = client or FakeResponses()
    jobs = plan_jobs(
        config.inputs, config.output_format, config.output_dir, input_extensions=backend.info.input_extensions
    )
    return Pipeline(config, console, backend=backend(config, client)).run(jobs), client


# -- registration and config ------------------------------------------------


def test_both_routes_are_registered():
    assert get_backend("openai") is OpenAIBackend
    assert get_backend("openrouter") is OpenRouterBackend
    assert set(BACKENDS) == {"datalab", "mistral", "openai", "openrouter"}


def test_info_describes_the_responses_api():
    info = OpenAIBackend.info
    assert info.input_extensions == {"pdf", "png", "jpg", "jpeg", "webp", "gif"}
    assert info.output_formats == {"markdown", "html"}
    assert info.modes == ("fast", "balanced", "accurate")
    assert info.max_upload_bytes == 50 * 1024 * 1024
    assert (info.chunk_size, info.default_model) == (5, "gpt-6-luna")
    assert info.api_key_env_vars == ("OPENAI_API_KEY",)
    router = OpenRouterBackend.info
    assert (router.name, router.label, router.default_model) == (
        "openrouter",
        "OpenRouter",
        "openai/gpt-6-luna",
    )
    assert router.api_key_env_vars == ("OPENROUTER_API_KEY",)


def test_config_is_checked_against_the_backend(tmp_path):
    with pytest.raises(ConfigurationError, match="OpenAI backend cannot produce json"):
        Config(inputs=[tmp_path], backend="openai", api_key="k", output_format="json").validate()
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        Config(inputs=[tmp_path], backend="openrouter").validate()
    with pytest.raises(ConfigurationError, match="Datalab backend does not take --model"):
        Config(inputs=[tmp_path], api_key="k", model="gpt-6-luna").validate()


def test_from_config_builds_a_client_for_each_route(tmp_path):
    for backend, url in (
        (OpenAIBackend, "https://api.openai.com/v1"),
        (OpenRouterBackend, "https://openrouter.ai/api/v1"),
    ):
        config = Config(inputs=[tmp_path], backend=backend.info.name, api_key="k", timeout=30).validate()
        built = backend.from_config(config, threading.Event())
        assert isinstance(built.client, OpenAIClient)
        assert (built.client.base_url, built.client.label, built.client.timeout) == (
            url,
            backend.info.label,
            30,
        )


# -- requests ------------------------------------------------------------------


def test_pdf_chunks_are_sent_as_files(examples, console):
    summary, client = run([examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=2)
    assert summary.exit_code == 0
    first, second = sorted(client.bodies, key=lambda b: b["input"][0]["content"][0]["filename"])
    part = first["input"][0]["content"][0]
    assert part["type"] == "input_file" and part["detail"] == "high"
    assert base64.b64decode(part["file_data"].split(",", 1)[1]).startswith(b"%PDF")
    assert part["file_data"].startswith("data:application/pdf;base64,")
    assert first["model"] == "gpt-6-luna"
    assert first["reasoning"] == {"effort": "low"}
    assert first["store"] is False
    assert first["text"]["format"]["type"] == "json_schema" and first["text"]["format"]["strict"]
    assert "in order: 2 pages." in first["instructions"] and "in order: 1 page." in second["instructions"]
    assert "plugins" not in first


def test_images_are_sent_as_one_page(tmp_path, console):
    (tmp_path / "scan.png").write_bytes(PNG_BYTES)
    summary, client = run([tmp_path], console)
    assert summary.exit_code == 0
    (body,) = client.bodies
    part = body["input"][0]["content"][0]
    assert part["type"] == "input_image" and part["image_url"].startswith("data:image/png;base64,")
    assert "in order: 1 page." in body["instructions"]
    assert (tmp_path / "scan.md").read_text() == "image page 0\n"


def test_options_shape_the_request(examples, console):
    _, client = run(
        [examples / "equations.pdf"],
        console,
        mode="accurate",
        model="gpt-5.6-luna",
        disable_image_captions=True,
        extra_options={
            "service_tier": "flex",
            "max_output_tokens": "20000",
            "reasoning": '{"effort": "high"}',
        },
    )
    (body,) = client.bodies
    assert body["model"] == "gpt-5.6-luna"
    assert body["service_tier"] == "flex"
    assert body["max_output_tokens"] == 20000  # JSON values are decoded
    assert body["reasoning"] == {"effort": "high"}  # and override the defaults
    assert "Leave out illustrations" in body["instructions"]


@pytest.mark.parametrize(("mode", "effort"), [("fast", "none"), ("balanced", "low"), ("accurate", "medium")])
def test_modes_set_reasoning_effort(examples, console, mode, effort):
    _, client = run([examples / "equations.pdf"], console, mode=mode)
    assert client.bodies[0]["reasoning"] == {"effort": effort}


def test_openrouter_prefixes_models_and_pins_native_pdf_parsing(examples, console):
    _, client = run([examples / "equations.pdf"], console, backend=OpenRouterBackend)
    assert client.bodies[0]["model"] == "openai/gpt-6-luna"
    assert client.bodies[0]["plugins"] == [{"id": "file-parser", "pdf": {"engine": "native"}}]
    for model, sent in (("gpt-5.6-luna", "openai/gpt-5.6-luna"), ("google/other", "google/other")):
        _, client = run(
            [examples / "equations.pdf"], console, backend=OpenRouterBackend, model=model, overwrite=True
        )
        assert client.bodies[0]["model"] == sent
    plugins = '[{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]'
    _, client = run(
        [examples / "equations.pdf"],
        console,
        backend=OpenRouterBackend,
        extra_options={"plugins": plugins},
        overwrite=True,
    )
    assert client.bodies[0]["plugins"][0]["pdf"] == {"engine": "mistral-ocr"}  # --api-option wins


def test_instructions_follow_the_output_format():
    markdown = instructions_for("markdown", 3, describe_figures=True)
    assert "in order: 3 pages." in markdown and "GitHub-flavored Markdown tables" in markdown
    assert "one-sentence description" in markdown
    html = instructions_for("html", 1, describe_figures=False)
    assert "in order: 1 page." in html and "<table>" in html and "Leave out illustrations" in html


def test_unsupported_file_types_are_rejected_locally(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"x")
    request = TranscribeRequest("gpt-6-luna", "markdown", 1, "low")
    with pytest.raises(APIError, match="Unsupported file type"):
        request.body(path)


# -- responses -----------------------------------------------------------------


def test_split_pdfs_merge_with_source_page_numbers(examples, console):
    summary, _ = run([examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=1, paginate=True)
    assert summary.exit_code == 0
    text = (examples / "alice_in_wonderland_sample.md").read_text()
    assert [int(n) for n in MARKER.findall(text)] == [0, 1, 2]
    assert "0001of0003.pdf page 0" in text and "0003of0003.pdf page 0" in text
    assert "3 pages" in console.err


def test_html_output_wraps_each_page(examples, console):
    summary, _ = run(
        [examples / "alice_in_wonderland_sample.pdf"], console, chunk_size=2, output_format="html"
    )
    assert summary.exit_code == 0
    html = (examples / "alice_in_wonderland_sample.html").read_text()
    assert html.count("<body") == 1
    assert re.findall(r'data-page-id="(\d+)"', html) == ["0", "1", "2"]


def test_join_pages():
    assert join_pages(["a\n", "", " b"], "markdown", paginate=False) == "a\n\nb"
    paginated = join_pages(["a", ""], "markdown", paginate=True)
    assert MARKER.findall(paginated) == ["0", "1"]
    html = join_pages(["<p>a</p>"], "html", paginate=False)
    assert '<div class="page" data-page-id="0">\n<p>a</p>\n</div>' in html


def test_wrong_page_count_is_retried_once(examples, console):
    def responder(body, index):
        return payload(["only one"] if index == 0 else ["a", "b", "c"])

    summary, client = run([examples / "alice_in_wonderland_sample.pdf"], console, FakeResponses(responder))
    assert summary.exit_code == 0 and len(client.bodies) == 2
    assert (examples / "alice_in_wonderland_sample.md").read_text() == "a\n\nb\n\nc\n"


def test_wrong_page_count_twice_fails_the_file(examples, console):
    summary, client = run(
        [examples / "alice_in_wonderland_sample.pdf"],
        console,
        FakeResponses(lambda body, i: payload(["x"] * 4)),
    )
    assert summary.exit_code == 1 and len(client.bodies) == 2
    assert "returned 4 pages for 3 (try a smaller --chunk-size)" in console.err


def test_cost_is_reported(examples, console):
    usage = {"input_tokens": 200_000, "output_tokens": 100_000}
    summary, _ = run(
        [examples / "equations.pdf"], console, FakeResponses(lambda body, i: payload(["x"], usage=usage))
    )
    assert summary.cost_cents == pytest.approx(7.0)  # $0.02 in + $0.05 out


def test_fatal_errors_stop_the_run(examples, console):
    with pytest.raises(FatalAPIError):
        run([examples], console, FakeResponses(lambda body, i: FatalAPIError("bad key")))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            payload([], status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
            "smaller --chunk-size",
        ),
        (payload([], status="incomplete", incomplete_details={"reason": "content_filter"}), "stopped early"),
        ({"status": "failed", "error": {"message": "server exploded"}}, "response failed: server exploded"),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}],
            },
            "refused: no",
        ),
        (
            {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{"}]}],
            },
            "malformed",
        ),
        ({"status": "completed", "output": []}, "malformed"),
        (
            {
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": '{"pages": [1]}'}]}
                ],
            },
            "not a list of strings",
        ),
    ],
)
def test_bad_responses_are_errors(data, message):
    with pytest.raises(APIError, match=re.escape(message)):
        parse_response(data, "gpt-6-luna")


def test_cost_cents():
    usage = {
        "input_tokens": 200_000,
        "input_tokens_details": {"cached_tokens": 40_000, "cache_write_tokens": 60_000},
        "output_tokens": 100_000,
    }
    # 100k uncached at $0.10, 40k cached at $0.01, 60k written at $0.125, 100k out at $0.50
    standard = (0.01 + 0.0004 + 0.0075 + 0.05) * 100
    assert cost_cents("gpt-6-luna", usage, "default") == pytest.approx(standard)
    assert cost_cents("gpt-6-luna-2026-05-18", usage, "default") == pytest.approx(standard)
    assert cost_cents("gpt-6-luna", usage, "flex") == pytest.approx(standard / 2)
    long = {"input_tokens": 300_000, "output_tokens": 10_000}
    assert cost_cents("gpt-6-luna", long, None) == pytest.approx((0.06 + 0.0075) * 100)
    assert cost_cents("gpt-6-luna", usage, "priority") is None
    assert cost_cents("some-other-model", usage, "default") is None
    assert cost_cents("openai/gpt-6-luna", {"cost": 0.0012}, "default") == pytest.approx(0.12)  # OpenRouter


def test_parse_response_uses_the_billed_model():
    result = parse_response(payload(["a"], model="gpt-5.6-luna", usage={"input_tokens": 100_000}), "x")
    assert result.pages == ["a"]
    assert result.cost_cents == pytest.approx(2.0)  # gpt-5.6-luna input is $0.20


def test_chunk_page_count_defaults_to_one_for_images(tmp_path):
    config = Config(inputs=[tmp_path], backend="openai", api_key="k").validate()
    request = OpenAIBackend(config, FakeResponses()).request_for(Chunk(tmp_path / "a.png"))
    assert request.page_count == 1
