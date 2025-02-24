import hashlib
import logging
import os
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
    """Safely delete a file or directory."""
    try:
        path = Path(path)  # Convert to Path if string
        if not path.exists():
            return

        if path.is_file():
            path.unlink()
        elif path.is_dir():
            # Remove all files in directory recursively
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.error(f"Failed to delete {path}: {e}")


def get_file_size(path: Path) -> int:
    """Get file size in bytes."""
    try:
        return path.stat().st_size
    except Exception as e:
        logger.error(f"Error getting file size for {path}: {e}")
        return 0


def get_env_var(name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement."""
    value = os.getenv(name)
    if required and not value:
        raise FileError(f"Required environment variable {name} is not set")
    return value


class FileDiscovery:
    """Handles finding and filtering files based on various criteria."""
    
    @staticmethod
    def find_processable_files(input_path: Path, supported_types: Set[str], 
                              supported_extensions: Optional[List[str]] = None) -> List[Path]:
        """
        Find all processable files from an input path.
        
        Args:
            input_path: Directory or file path to search
            supported_types: Set of supported MIME types
            supported_extensions: List of supported file extensions (without dot)
            
        Returns:
            List of processable file paths
        """
        if supported_extensions is None:
            supported_extensions = ['.pdf', '.docx', '.doc', '.pptx', '.ppt', 
                                   '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff']
        
        files_to_process = []
        
        # Helper function to check file type without loading entire file
        def check_file_type(file_path: Path) -> Optional[filetype.Type]:
            try:
                # Only read first 8KB for type detection rather than the whole file
                with open(file_path, 'rb') as f:
                    header = f.read(8192)  # First 8KB is enough for type detection
                return filetype.guess(header)
            except Exception as e:
                logger.warning(f"Error reading file header for {file_path}: {e}")
                return None
        
        # If input is a file, validate and return it
        if input_path.is_file():
            try:
                kind = check_file_type(input_path)
                if (kind and kind.mime in supported_types) or \
                   (input_path.suffix.lower() in supported_extensions):
                    files_to_process.append(input_path)
                else:
                    logger.warning(f"Unsupported file type: {input_path}")
            except Exception as e:
                logger.warning(f"Error checking file {input_path}: {e}")
            
            return files_to_process
            
        # If input is a directory, find all matching files
        if not input_path.exists():
            raise FileError(f"Input path does not exist: {input_path}")
            
        # Process directory
        for p in input_path.glob("**/*"):
            if p.is_file():
                try:
                    kind = check_file_type(p)
                    if (kind and kind.mime in supported_types):
                        files_to_process.append(p)
                    elif p.suffix.lower() in supported_extensions:
                        # Some file types might not be detected correctly by filetype
                        files_to_process.append(p)
                except Exception as e:
                    logger.warning(f"Error checking file type for {p}: {e}")
                    
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
    def read_text(path: Path, encoding: str = 'utf-8') -> str:
        """Read a file's content as text."""
        try:
            return path.read_text(encoding=encoding)
        except Exception as e:
            raise FileError(f"Failed to read file {path}: {e}")
        
    @staticmethod
    def write_file(path: Path, content: str, encoding: str = 'utf-8') -> None:
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