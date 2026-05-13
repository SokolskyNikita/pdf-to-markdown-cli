import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# import os # Not used

from docs_to_md.utils.exceptions import FileError
from docs_to_md.api.models import SUPPORTED_FORMAT_EXTENSIONS

logger = logging.getLogger(__name__)


def generate_unique_key(length: int = 8) -> str:
    """Generate a short unique key for output file naming."""
    return uuid.uuid4().hex[:length]


@dataclass(frozen=True)
class OutputPaths:
    """Holds the determined output paths for a conversion."""

    markdown_path: Path
    images_dir: Path
    unique_key: str # Add the key for potential later use


def determine_output_paths(
    input_file: Path, output_dir_config: Optional[Path], output_format: str
) -> OutputPaths:
    """
    Determines the final output markdown path and images directory path
    using a unique key for each run.
    The image directory path is determined but not created here.
    """
    if not input_file.is_file():
        raise ValueError(f"Input path must be a file: {input_file}")

    base_output_dir = output_dir_config if output_dir_config else input_file.parent
    try:
        # Still ensure the base output directory exists
        base_output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise FileError(
            f"Could not create or access base output directory {base_output_dir}: {e}"
        ) from e

    extension = SUPPORTED_FORMAT_EXTENSIONS.get(output_format)
    if not extension:
        raise FileError(f"Unsupported output format: {output_format}")
    file_extension = extension.lstrip(".")

    markdown_filename_base = input_file.stem
    while True:
        unique_key = generate_unique_key()
        final_output_filename = f"{markdown_filename_base}_{unique_key}.{file_extension}"
        final_output_path = base_output_dir / final_output_filename
        final_images_dir = base_output_dir / f"images_{unique_key}"
        if not final_output_path.exists() and not final_images_dir.exists():
            break

    logger.debug(f"Determined final output path: {final_output_path}")

    # Note: The image directory is NOT created here.
    # Creation should happen later, only if images are actually extracted.

    logger.info(
        f"Determined final paths: Output='{final_output_path}', Images='{final_images_dir}'"
    )

    return OutputPaths(
        markdown_path=final_output_path,
        images_dir=final_images_dir,
        unique_key=unique_key
    )
