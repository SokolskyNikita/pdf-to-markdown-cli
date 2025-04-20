import logging
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Set

import filetype

from docs_to_md.utils.exceptions import FileError

logger = logging.getLogger(__name__)


def ensure_directory(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def safe_delete(path: Path) -> None:
    """Safely delete a file or directory, ignoring errors."""
    try:
        path = Path(path)
        if path.exists():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.error(f"Error preparing to delete {path}: {e}", exc_info=False)


def get_unique_filename(path: Path) -> Path:
    """Generates a unique filename if the path exists by appending _1, _2, etc."""
    if not path.exists():
        return path

    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    counter = 1

    max_attempts = 1000
    while counter <= max_attempts:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = parent / new_filename
        if not new_path.exists():
            return new_path
        counter += 1

    logger.error(f"Could not find unique filename for {path.name} after {max_attempts} attempts.")
    return parent / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


class FileDiscovery:
    """Handles finding and filtering files based on various criteria."""

    @staticmethod
    def _check_file_type(file_path: Path) -> Optional[filetype.Type]:
        """Reads file header to guess MIME type. Internal helper."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(8192)
            if not header:
                logger.debug(f"File {file_path} is empty, cannot guess MIME type.")
                return None
            return filetype.guess(header)
        except FileNotFoundError:
            logger.warning(f"File not found during type check: {file_path}")
            return None
        except PermissionError:
            logger.warning(f"Permission denied reading file header: {file_path}")
            return None
        except Exception as e:
            logger.warning(f"Error reading file header for {file_path}: {e}", exc_info=False)
            return None

    @staticmethod
    def _is_processable(
        file_path: Path,
        supported_extensions: Set[str],
        supported_types: Set[str]
    ) -> bool:
        """Checks if a single file is processable based on extension and MIME type."""
        ext = file_path.suffix.lower().strip('.')
        if ext not in supported_extensions:
            return False

        kind = FileDiscovery._check_file_type(file_path)

        if kind and kind.mime in supported_types:
            logger.debug(f"Adding {file_path}: Supported extension '{ext}' and MIME type '{kind.mime}'.")
            return True
        elif kind:
            logger.warning(f"Skipping {file_path}: Supported extension '{ext}', but unsupported detected MIME type '{kind.mime}'.")
            return False
        else:
            logger.info(f"Skipping {file_path}: Supported extension '{ext}', but MIME detection failed or ambiguous.")
            return False

    @staticmethod
    def find_processable_files(
        input_path: Path,
        supported_types: Set[str],
        supported_extensions: Set[str],
    ) -> List[Path]:
        """
        Finds all processable files from an input path (file or directory).

        Args:
            input_path: Directory or file path to search.
            supported_types: Set of supported MIME types.
            supported_extensions: Set of supported file extensions (without dot).

        Returns:
            List of processable file paths.

        Raises:
            FileError: If the input path does not exist or is invalid.
        """
        files_to_process = []
        input_path = Path(input_path).resolve()

        if not input_path.exists():
            raise FileError(f"Input path does not exist: {input_path}")

        if input_path.is_file():
            if FileDiscovery._is_processable(input_path, supported_extensions, supported_types):
                files_to_process.append(input_path)
            else:
                ext = input_path.suffix.lower().strip('.')
                if ext not in supported_extensions:
                    logger.warning(f"Input file skipped: Unsupported extension '{ext}' in {input_path}")

        elif input_path.is_dir():
            logger.info(f"Searching for processable files in directory: {input_path}")
            for p in input_path.rglob("*"):
                if p.is_file():
                    if FileDiscovery._is_processable(p, supported_extensions, supported_types):
                        files_to_process.append(p)

        else:
            raise FileError(f"Input path is neither a file nor a directory: {input_path}")

        if not files_to_process:
            logger.warning(f"No processable files found matching criteria in: {input_path}")
        else:
            logger.info(f"Found {len(files_to_process)} processable file(s) in {input_path}")

        return files_to_process


class TemporaryDirectory:
    """Context manager for temporary directories."""

    def __init__(self, base_path: Path, prefix: str):
        """
        Initialize a temporary directory.

        Args:
            base_path: Base path where to create the temporary directory
            prefix: Prefix for the directory name
        """
        self.path = base_path / f"{prefix}_{uuid.uuid4().hex[:8]}"
        ensure_directory(self.path)

    def __enter__(self) -> Path:
        """Enter the context and return the path to the temporary directory."""
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up the temporary directory when exiting the context."""
        safe_delete(self.path)


class FileIO:
    """Utility class for file operations."""

    @staticmethod
    def read_file(path: Path) -> bytes:
        """Read a file's content as bytes."""
        try:
            return path.read_bytes()
        except Exception as e:
            raise FileError(f"Failed to read file {path}: {e}")

    @staticmethod
    def read_text(path: Path, encoding: str = "utf-8") -> str:
        """Read a file's content as text."""
        try:
            return path.read_text(encoding=encoding)
        except Exception as e:
            raise FileError(f"Failed to read file {path}: {e}")

    @staticmethod
    def write_file(path: Path, content: str, encoding: str = "utf-8") -> None:
        """Write text content to a file."""
        try:
            ensure_directory(path.parent)
            path.write_text(content, encoding=encoding)
        except Exception as e:
            raise FileError(f"Failed to write to file {path}: {e}")

    @staticmethod
    def write_binary(path: Path, content: bytes) -> None:
        """Write binary content to a file."""
        try:
            ensure_directory(path.parent)
            path.write_bytes(content)
        except Exception as e:
            raise FileError(f"Failed to write binary data to {path}: {e}")

    @staticmethod
    def copy_file(src: Path, dst: Path) -> None:
        """Copy a file from source to destination."""
        try:
            ensure_directory(dst.parent)
            shutil.copy2(src, dst)
        except Exception as e:
            raise FileError(f"Failed to copy file from {src} to {dst}: {e}")
