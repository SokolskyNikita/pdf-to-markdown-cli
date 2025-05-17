import os
import tempfile
import unittest
from pathlib import Path

from docs_to_md.core.paths import determine_output_paths


class TestPaths(unittest.TestCase):
    def test_determine_output_paths_creates_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_file = tmp_path / "input.txt"
            input_file.write_text("data")
            out_dir = tmp_path / "out"
            result = determine_output_paths(input_file, out_dir, "markdown")
            self.assertEqual(result.markdown_path.parent, out_dir)
            self.assertEqual(result.images_dir.parent, out_dir)
            self.assertTrue(result.unique_key)
            self.assertEqual(result.markdown_path.suffix, ".md")
            self.assertTrue(out_dir.exists())


if __name__ == "__main__":
    unittest.main()
