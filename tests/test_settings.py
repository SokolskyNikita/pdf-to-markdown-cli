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

    def test_config_falls_back_when_cache_dir_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "input.txt"
            test_file.write_text("data")

            # File path cannot be created as a directory, forcing fallback.
            cache_dir_as_file = tmp_path / "cache"
            cache_dir_as_file.write_text("not-a-directory")

            cfg = Config(
                api_key="key",
                input_path=str(test_file),
                output_dir=tmp_path,
                output_format="markdown",
                cache_dir=cache_dir_as_file,
                root_tmp_dir=tmp_path / "tmp",
            )
            cfg.validate()

            expected_cache_dir = (
                Path(tempfile.gettempdir()) / ".docs_to_md" / "cache"
            ).resolve(strict=False)
            self.assertEqual(cfg.cache_dir, expected_cache_dir)
            self.assertTrue(cfg.root_tmp_dir.exists())


if __name__ == "__main__":
    unittest.main()
