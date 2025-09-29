import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from docs_to_md.utils.file_utils import get_unique_filename
from docs_to_md.core.result_handler import ResultSaver
from docs_to_md.storage.models import ConversionRequest, Status


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


class TestImageDirectoryCreation(unittest.TestCase):
    def setUp(self):
        self.saver = ResultSaver()

    def test_image_directory_not_created_when_no_images(self):
        """Test that image directory is not created when no images exist."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Create a mock conversion request with no images
            target_file = tmp_path / "output.md"
            images_dir = tmp_path / "images_test123"
            tmp_dir = tmp_path / "temp"
            tmp_dir.mkdir()
            
            request = ConversionRequest(
                request_id="test-request",
                original_file=tmp_path / "input.pdf",
                target_file=target_file,
                output_format="markdown",
                status=Status.COMPLETE,
                chunk_size=1,
                tmp_dir=tmp_dir,
                images_dir=images_dir
            )
            
            # Add a chunk to the request
            chunk = request.add_chunk(tmp_path / "input.pdf", 0)
            
            # Create the result file that the chunk expects
            chunk_result = chunk.get_result_path(tmp_dir)
            chunk_result.write_text("# Test Content\n\nSome markdown content.")
            chunk.mark_complete()
            
            # Combine results - should NOT create images directory
            result_file, size = self.saver.combine_results(request)
            
            # Verify the markdown file was created
            self.assertTrue(result_file.exists())
            self.assertGreater(size, 0)
            
            # Verify the images directory was NOT created
            self.assertFalse(images_dir.exists(), 
                           f"Images directory {images_dir} should not be created when no images exist")

    def test_image_directory_created_when_images_exist(self):
        """Test that image directory is created when images exist."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Create a mock conversion request with images
            target_file = tmp_path / "output.md"
            images_dir = tmp_path / "images_test456"
            tmp_dir = tmp_path / "temp"
            tmp_dir.mkdir()
            
            # Create temporary images directory with a test image
            temp_images_dir = tmp_dir / "images"
            temp_images_dir.mkdir()
            test_image = temp_images_dir / "test_image.png"
            test_image.write_bytes(b"fake image data")
            
            request = ConversionRequest(
                request_id="test-request-with-images",
                original_file=tmp_path / "input.pdf",
                target_file=target_file,
                output_format="markdown",
                status=Status.COMPLETE,
                chunk_size=1,
                tmp_dir=tmp_dir,
                images_dir=images_dir
            )
            
            # Add a chunk to the request
            chunk = request.add_chunk(tmp_path / "input.pdf", 0)
            
            # Create the result file that the chunk expects
            chunk_result = chunk.get_result_path(tmp_dir)
            chunk_result.write_text("# Test Content\n\nSome markdown content.")
            chunk.mark_complete()
            
            # Combine results - should create images directory
            result_file, size = self.saver.combine_results(request)
            
            # Verify the markdown file was created
            self.assertTrue(result_file.exists())
            self.assertGreater(size, 0)
            
            # Verify the images directory WAS created
            self.assertTrue(images_dir.exists(), 
                          f"Images directory {images_dir} should be created when images exist")


if __name__ == "__main__":
    unittest.main()
