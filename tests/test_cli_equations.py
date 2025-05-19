import sys
import types
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Stub external dependencies before importing the package
sys.modules['backoff'] = types.SimpleNamespace(on_exception=lambda *a, **k: (lambda f: f), expo=lambda *a, **k: None)
sys.modules['requests'] = types.SimpleNamespace(exceptions=types.SimpleNamespace(RequestException=Exception), post=lambda *a, **k: None, get=lambda *a, **k: None)
sys.modules['ratelimit'] = types.SimpleNamespace(limits=lambda *a, **k: (lambda f: f), sleep_and_retry=lambda f: f)
class DummyCache(dict):
    def __init__(self, *a, **k):
        pass
    def set(self, k, v):
        super().__setitem__(k, v)
    def get(self, k, default=None):
        return super().get(k, default)
    def delete(self, k):
        return super().pop(k, None)
    def iterkeys(self):
        return iter(self.keys())
    def close(self):
        pass
sys.modules['diskcache'] = types.SimpleNamespace(Cache=DummyCache)
sys.modules['pikepdf'] = types.SimpleNamespace(Pdf=type('Pdf', (), {'open': lambda *a, **k: type('PDF', (), {'pages': []})(), 'new': lambda: type('PDF', (), {'pages': []})(), 'ObjectStreamMode': type('O', (), {'generate': None})}), PdfError=Exception, ObjectStreamMode=type('O', (), {'generate': None}))
class DummyTqdm:
    def __init__(self, *a, **k):
        pass
    def update(self, *a, **k):
        pass
    def close(self):
        pass
sys.modules['tqdm'] = types.SimpleNamespace(tqdm=DummyTqdm)

# Patch pdf splitter to avoid real PDF processing
def dummy_chunk_pdf_to_temp(*args, **kwargs):
    return None

class DummyCacheManager:
    def __init__(self, *a, **k):
        self.store = {}

    def save(self, request):
        self.store[request.request_id] = request

    def get(self, request_id):
        return self.store.get(request_id)

    def delete(self, request_id):
        return bool(self.store.pop(request_id, None))

    def get_all(self):
        return list(self.store.values())

    def close(self):
        pass

from docs_to_md.config.settings import Config
from docs_to_md.core.processor import MarkerProcessor
from docs_to_md.api.models import MarkerStatus, StatusEnum
from docs_to_md.storage import cache as cache_module


class FakeMarkerClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def submit_file(self, *args, **kwargs):
        return "req-1"

    def check_status(self, request_id: str):
        return MarkerStatus(status=StatusEnum.COMPLETE, markdown="# mock", success=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestCLIOperation(unittest.TestCase):
    def test_process_equations_pdf(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_pdf = Path("examples/equations.pdf")
            env = {"MARKER_PDF_KEY": "test"}
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch("docs_to_md.core.processor.MarkerClient", FakeMarkerClient):
                    with mock.patch("docs_to_md.core.result_handler.time.sleep", return_value=None):
                        with mock.patch("docs_to_md.core.processor.CacheManager", DummyCacheManager):
                            with mock.patch("docs_to_md.core.processor.chunk_pdf_to_temp", dummy_chunk_pdf_to_temp):
                                from tests.filetype import Type
                                with mock.patch("filetype.guess", return_value=Type("application/pdf")):
                                    cfg = Config(
                                        api_key=env["MARKER_PDF_KEY"],
                                        input_path=str(input_pdf),
                                        output_dir=Path(tmp_dir),
                                        output_format="markdown",
                                        chunk_size=1000,
                                    )
                                    cfg.validate()
                                    processor = MarkerProcessor(cfg)
                                    processor.process()

            md_files = list(Path(tmp_dir).glob("*.md"))
            self.assertEqual(len(md_files), 1)
            content = md_files[0].read_text().strip()
            self.assertIn("# mock", content)


if __name__ == "__main__":
    unittest.main()
