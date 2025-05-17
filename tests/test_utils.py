import tempfile
import unittest
from pathlib import Path

from docs_to_md.utils.file_utils import get_unique_filename


class TestFileUtils(unittest.TestCase):
    def test_get_unique_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_path = tmp_path / "file.txt"
            file_path.write_text("data")
            new_path = get_unique_filename(file_path)
            self.assertNotEqual(new_path, file_path)
            self.assertEqual(new_path.parent, file_path.parent)
            self.assertTrue(new_path.stem.startswith("file_"))
            self.assertEqual(new_path.suffix, ".txt")


if __name__ == "__main__":
    unittest.main()
