import tempfile
import unittest
from pathlib import Path

from docs_to_md.config.settings import Config
from docs_to_md.utils.exceptions import ConfigurationError


class TestSettings(unittest.TestCase):
    def test_config_validation_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "input.txt"
            test_file.write_text("data")
            cfg = Config(
                api_key="key",
                input_path=str(test_file),
                output_dir=tmp_path,
                output_format="markdown",
            )
            cfg.validate()

    def test_config_missing_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "in.txt"
            test_file.write_text("x")
            cfg = Config(
                api_key="",
                input_path=str(test_file),
                output_dir=tmp_path,
                output_format="markdown",
            )
            with self.assertRaises(ConfigurationError):
                cfg.validate()

    def test_config_nonexistent_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = Config(
                api_key="key",
                input_path=str(tmp_path / "no.txt"),
                output_dir=tmp_path,
                output_format="markdown",
            )
            with self.assertRaises(ConfigurationError):
                cfg.validate()

    def test_config_relative_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "file.txt"
            test_file.write_text("x")
            cfg = Config(
                api_key="key",
                input_path=str(test_file),
                output_dir=Path("relative"),
                output_format="markdown",
            )
            with self.assertRaises(ConfigurationError):
                cfg.validate()


if __name__ == "__main__":
    unittest.main()
