import logging
import os
from pathlib import Path
from typing import List, Optional


def ensure_directory(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)

def get_file_paths(input_path: str, pattern: str = "*") -> List[str]:
    """Get list of file paths matching pattern from input path."""
    path = Path(input_path)
    if not path.exists():
        raise ValueError(f"Input path does not exist: {input_path}")

    if path.is_file():
        return [str(path)]
    elif path.is_dir():
        files = [str(p) for p in path.glob(f"**/{pattern}") if p.is_file()]
        if not files:
            raise ValueError(f"No files found in directory: {input_path}")
        return files
    else:
        raise ValueError(f"Invalid input path: {input_path}")

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
            for item in path.rglob("*"):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    item.rmdir()
            # Remove the directory itself
            path.rmdir()
    except Exception as e:
        logging.error(f"Failed to delete {path}: {e}")

def get_file_size(path: Path) -> int:
    """Get file size in bytes."""
    try:
        return path.stat().st_size
    except Exception as e:
        logging.error(f"Error getting file size for {path}: {e}")
        return 0

def get_env_var(name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement."""
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value