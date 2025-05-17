import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docs_to_md.config.cli import create_config_from_args


class TestCLI(unittest.TestCase):
    def test_create_config_from_args(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.txt"
            input_file.write_text("data")
            env = {"MARKER_PDF_KEY": "abc"}
            argv = [
                "prog",
                str(input_file),
                "-cs",
                "5",
                "--max",
                "-o",
                tmp_dir,
            ]
            with mock.patch.dict(os.environ, env, clear=False):
                with mock.patch.object(sys, "argv", argv):
                    config = create_config_from_args()
            self.assertEqual(config.input_path, str(input_file))
            self.assertEqual(config.chunk_size, 5)
            self.assertTrue(config.use_llm)
            self.assertTrue(config.force_ocr)
            self.assertEqual(config.output_dir, Path(tmp_dir))


if __name__ == "__main__":
    unittest.main()
