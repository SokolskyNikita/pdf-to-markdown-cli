import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# import os # Not used

from docs_to_md.utils.exceptions import FileError
from docs_to_md.api.models import SUPPORTED_FORMAT_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutputPaths:
    """Holds the determined output paths for a conversion."""

    markdown_path: Path
    images_dir: Path


def find_unique_path(
    base_dir: Path, name: str, extension: Optional[str] = None, is_dir: bool = False
) -> Path:
    """Finds a unique path by appending _1, _2, etc., if necessary."""
    counter = 0
    unique_name = name

    while True:
        if counter > 0:
            unique_name = f"{name}_{counter}"

        target_name = (
            f"{unique_name}.{extension}" if extension and not is_dir else unique_name
        )
        target_path = base_dir / target_name

        path_exists = target_path.is_dir() if is_dir else target_path.exists()

        if not path_exists:
            # Attempt to create the directory immediately if it's a directory path we're checking
            # This prevents race conditions if multiple processes check simultaneously
            if is_dir:
                try:
                    target_path.mkdir(parents=False, exist_ok=False)
                    logger.debug(
                        f"Successfully created unique directory: {target_path}"
                    )
                    return target_path
                except FileExistsError:
                    # Directory was created between the check and mkdir, loop again
                    logger.debug(
                        f"Directory {target_path} was created by another process, retrying."
                    )
                    pass
                except OSError as e:
                    logger.error(f"Failed to create directory {target_path}: {e}")
                    raise  # Reraise unexpected errors
            else:
                return target_path  # For files, just return the non-existent path

        counter += 1
        if counter > 1000:  # Safety break
            raise OSError(
                f"Could not find a unique path for {name} in {base_dir} after 1000 attempts."
            )


def determine_output_paths(
    input_file: Path, output_dir_config: Optional[Path], output_format: str
) -> OutputPaths:
    """
    Determines the final output markdown path and images directory path,
    handling collisions by appending suffixes (_1, _2, ...).
    Ensures the final image directory exists.
    """
    if not input_file.is_file():
        raise ValueError(f"Input path must be a file: {input_file}")

    base_output_dir = output_dir_config if output_dir_config else input_file.parent
    try:
        base_output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise FileError(
            f"Could not create or access base output directory {base_output_dir}: {e}"
        ) from e

    # Use the imported mapping to get the desired file extension (remove the leading dot)
    file_extension = SUPPORTED_FORMAT_EXTENSIONS.get(output_format, output_format)
    if file_extension.startswith("."):
        file_extension = file_extension[1:]  # Remove leading dot if present

    markdown_filename_base = input_file.stem
    final_markdown_path = find_unique_path(
        base_dir=base_output_dir,
        name=markdown_filename_base,
        extension=file_extension,  # Use the mapped extension
        is_dir=False,
    )
    logger.debug(f"Determined final markdown path: {final_markdown_path}")

    # Save to /images -- or into images_n if it already exists
    image_dir_base_name = "images"

    final_images_dir = find_unique_path(
        base_dir=base_output_dir, name=image_dir_base_name, is_dir=True
    )

    logger.info(
        f"Determined final paths: Markdown='{final_markdown_path}', Images='{final_images_dir}'"
    )

    return OutputPaths(markdown_path=final_markdown_path, images_dir=final_images_dir)
