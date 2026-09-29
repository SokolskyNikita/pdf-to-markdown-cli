from __future__ import annotations

import base64
import io
import shutil
import threading
from pathlib import Path

import pytest

from docs_to_md.assemble import ChunkOutput
from docs_to_md.backends import Backend, BackendInfo
from docs_to_md.backends.datalab.models import ConvertResult
from docs_to_md.console import Console
from docs_to_md.errors import Cancelled

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


@pytest.fixture
def examples(tmp_path: Path) -> Path:
    """A scratch copy of the bundled example PDFs (3-page and 1-page)."""
    target = tmp_path / "in"
    target.mkdir()
    for name in ("alice_in_wonderland_sample.pdf", "equations.pdf"):
        shutil.copy(EXAMPLES / name, target / name)
    return target


class CapturingConsole(Console):
    def __init__(self, quiet: bool = False):
        super().__init__(quiet=quiet, stdout=io.StringIO(), stderr=io.StringIO())

    @property
    def out(self) -> str:
        return self.stdout.getvalue()

    @property
    def err(self) -> str:
        return self.stderr.getvalue()


@pytest.fixture
def console() -> CapturingConsole:
    return CapturingConsole()


class FakeBackend(Backend):
    """A synchronous in-memory backend for testing the pipeline on its own.

    ``handler(chunk, check_cancelled)`` returns the chunk's ``ChunkOutput`` or
    raises. The default returns one image and ``<chunk file name>`` as content.
    """

    info = BackendInfo(
        name="fake",
        label="Fake",
        input_extensions=frozenset({"pdf", "docx", "pptx"}),
        output_formats=frozenset({"markdown", "html", "json"}),
    )

    def __init__(self, output_format: str = "markdown", handler=None):
        self.output_format = output_format
        self.handler = handler or self.default_handler
        self.chunks: list = []
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config, stop_event):
        return cls(config.output_format)

    def default_handler(self, chunk, check_cancelled):
        name = chunk.path.name
        content = {
            "markdown": f"# {name}\n\n![fig](img.png)\n",
            "html": f'<html><body><p>{name}</p><img src="img.png"/></body></html>',
            "json": {"children": [{"id": "/page/0/Page/0"}], "metadata": {}},
        }[self.output_format]
        return ChunkOutput(
            pages=chunk.pages,
            content=content,
            images={"img.png": PNG_B64},
            page_count=len(chunk.pages) or 1,
            cost_cents=0.3,
        )

    def convert(self, chunk, check_cancelled):
        check_cancelled()
        with self._lock:
            self.chunks.append(chunk)
        return self.handler(chunk, check_cancelled)


class FakeClient:
    """In-memory stand-in for DatalabClient.

    ``responder(path, options, call_index)`` returns the list of ConvertResult
    objects that successive status checks for that submission will see.
    """

    def __init__(self, responder=None):
        self.stop_event = threading.Event()
        self.submissions: list = []
        self._results: dict = {}
        self._lock = threading.Lock()
        self.responder = responder or self.default_responder

    @staticmethod
    def default_responder(path, options, index):
        return [
            ConvertResult(status="processing"),
            ConvertResult(
                status="complete",
                success=True,
                markdown=f"# {path.name}\n\n![fig](img.png)\n",
                html=f'<html><body><p>{path.name}</p><img src="img.png"/></body></html>',
                json={"children": [{"id": "/page/0/Page/0"}], "metadata": {"page_stats": []}},
                images={"img.png": PNG_B64},
                page_count=1,
                cost_cents=0.3,
            ),
        ]

    def submit(self, path, options):
        with self._lock:
            index = len(self.submissions)
            self.submissions.append((path, options))
            request_id = f"req-{index}"
            self._results[request_id] = list(self.responder(path, options, index))
        return request_id

    def get_result(self, request_id):
        with self._lock:
            queue = self._results[request_id]
            return queue.pop(0) if len(queue) > 1 else queue[0]

    def sleep(self, seconds):
        if self.stop_event.is_set():
            raise Cancelled("Interrupted")
