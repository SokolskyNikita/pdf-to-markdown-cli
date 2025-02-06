import base64
import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from tqdm import tqdm

from api_client import MarkerClient, MarkerStatus
from cache_manager import CacheManager, ChunkInfo, ConversionRequest, Status
from common import ensure_directory, safe_delete


class ResultSaver:
    def save_content(self, content: str, path: Path) -> None:
        """Save content to file, ensuring parent directory exists."""
        try:
            ensure_directory(path.parent)
            path.write_text(content, encoding='utf-8')
        except Exception as e:
            raise RuntimeError(f"Failed to save content to {path}: {e}")

class ResultHandler:
    # Output format to file extension mapping
    FORMAT_EXTENSIONS = {
        "markdown": ".md",
        "json": ".json",
        "html": ".html",
        "txt": ".txt"  # default
    }

    def __init__(self, api_key: str, cache_dir: Path, check_interval: int = 15):
        self.client = MarkerClient(api_key)
        self.cache = CacheManager(str(cache_dir))
        self.check_interval = check_interval
        self.saver = ResultSaver()

    def process_cache_items(self) -> None:
        reqs = self.cache.get_all()
        if not reqs:
            return

        for req in tqdm(reqs, desc="Processing requests"):
            try:
                # Skip already completed or failed requests
                if req.status in (Status.FAILED, Status.COMPLETE):
                    self._cleanup_request(req)
                    continue

                # Process any pending chunks
                if pending := req.pending_chunks:
                    self._process_pending_chunks(req, pending)

                # Try to combine results and cleanup if complete
                if req.all_complete:
                    self._combine_and_save_result(req)
                    self._cleanup_request(req)
                elif req.has_failed:
                    self._cleanup_request(req)
            except Exception as e:
                logging.error(f"Error processing request {req.request_id}: {e}")
                req.set_status(Status.FAILED, str(e))
                self._cleanup_request(req)

    def _process_pending_chunks(self, req: ConversionRequest, chunks: List[ChunkInfo]) -> None:
        logging.info(f"Processing {len(chunks)} chunks for {req.original_file.name}")
        for chunk in tqdm(chunks, desc="Processing chunks"):
            if self._process_chunk(chunk, req):
                req.set_status(Status.FAILED, chunk.error)
                break

    def _process_chunk(self, chunk: ChunkInfo, req: ConversionRequest) -> bool:
        """Process a chunk. Returns True if processing should stop."""
        if not req.tmp_dir:
            chunk.mark_failed("No temporary directory set for request")
            return True

        while True:
            status = self.client.check_status(chunk.request_id)
            if not status:
                chunk.mark_failed("Failed to get status from API")
                return True

            match status.status:
                case "failed":
                    chunk.mark_failed(status.error)
                    return True
                case "complete":
                    try:
                        self._save_chunk_result(chunk, status, req)
                        return False
                    except Exception as e:
                        chunk.mark_failed(str(e))
                        return True
                case _:
                    time.sleep(self.check_interval)

    def _save_chunk_result(self, chunk: ChunkInfo, status: MarkerStatus, req: ConversionRequest) -> None:
        content = None

        if status.markdown is not None:
            content = status.markdown
        elif status.json_data is not None:
            content = json.dumps(status.json_data)

        if not content:
            logging.error(f"No content found in result for chunk {chunk.path}")
            raise RuntimeError("No content in result")

        # Save content to temp file in request's tmp_dir
        temp_file = chunk.get_result_path(req.tmp_dir)
        
        def transform_image_name(original_name: str) -> Tuple[str, str]:
            """Transform image name and return (new_name, name_for_markdown)"""
            base_page_num = (chunk.index * req.chunk_size) + 1
            # Try to extract page and figure numbers
            page_match = re.search(r'_page_(\d+)', original_name)
            figure_match = re.search(r'Figure_(\d+)', original_name)
            extension = re.search(r'\.([a-z]+)$', original_name)
            
            if extension and extension.group(0):
                extension = extension.group(0)
            else:
                extension = ".jpeg"
            
            if page_match and figure_match:
                # Calculate new page number based on chunk position
                corrected_page_num = base_page_num + int(page_match.group(1))
                figure_num = int(figure_match.group(1))
                
                # Generate new filename with corrected page number
                new_name = f"_page_{corrected_page_num}_Figure_{figure_num}{extension}"
                return new_name, new_name
            else:
                # Fallback: use chunk number and random identifier
                random_suffix = uuid.uuid4().hex[:6]
                fallback_name = f"_chunk_{chunk.index}_{random_suffix}{extension}"
                return fallback_name, fallback_name

        # Update image references in content and prepare image saving
        transformed_images = {}
        if status.images:
            for original_name, b64_content in status.images.items():
                new_name, markdown_name = transform_image_name(original_name)
                transformed_images[new_name] = b64_content
                
                # Update references in the content
                content = content.replace(
                    f"]({original_name})",
                    f"](images/{markdown_name})"
                )

        logging.info(f"Saving chunk result to {temp_file}")
        self.saver.save_content(content, temp_file)
        chunk.mark_complete()

        # Save transformed images
        if transformed_images:
            images_dir = temp_file.parent / "images"
            logging.info(f"Saving {len(transformed_images)} images to {images_dir}")
            ensure_directory(images_dir)
            for name, b64 in transformed_images.items():
                try:
                    (images_dir / name).write_bytes(base64.b64decode(b64))
                except Exception as e:
                    logging.error(f"Failed to save image {name}: {e}")

    def _get_output_dir(self, req: ConversionRequest) -> Path:
        """Create and return output directory with timestamp."""
        timestamp = datetime.now().strftime("%y-%m-%d_%H-%M")
        base_dir = Path("converted")
        output_dir = base_dir / req.original_file.stem / timestamp
        ensure_directory(output_dir)
        return output_dir

    def _combine_and_save_result(self, req: ConversionRequest) -> None:
        """Combine chunk results and save final output."""
        try:
            # Combine all results
            contents = []
            logging.info(f"Combining results from {len(req.ordered_chunks)} chunks")
            for chunk in req.ordered_chunks:
                result_path = chunk.get_result_path(req.tmp_dir)
                if not result_path.exists():
                    raise RuntimeError(f"Result file does not exist: {result_path}")

                content = result_path.read_text()
                contents.append(content)

            # Create output directory and save result
            output_dir = self._get_output_dir(req)
            output_file = output_dir / f"{req.original_file.name}{self.FORMAT_EXTENSIONS.get(req.output_format, '.txt')}"

            # Save content
            combined_content = "\n\n".join(contents)
            if not combined_content.strip():
                raise RuntimeError("Combined content is empty")

            logging.info(f"Saving combined content ({len(combined_content)} chars) to {output_file}")
            self.saver.save_content(combined_content, output_file)
            logging.info(f"Successfully saved output to {output_file}")

            # Move images directory if it exists
            images_dir = req.tmp_dir / "images"
            if images_dir.exists():
                final_images = output_dir / "images"
                if final_images.exists():
                    safe_delete(final_images)

                images_dir.rename(final_images)
                logging.info(f"Moved images to {output_dir}/images/")

            req.set_status(Status.COMPLETE)
        except Exception as e:
            error_msg = f"Failed to combine results: {str(e)}"
            logging.error(error_msg)
            req.set_status(Status.FAILED, error_msg)
            raise

    def _cleanup_request(self, req: ConversionRequest) -> None:
        """Clean up temporary directory and cache entry."""
        try:
            # Clean up temp directory if it exists
            if req.tmp_dir and Path(req.tmp_dir).exists():
                safe_delete(req.tmp_dir)

            # Remove from cache
            self.cache.delete(req.request_id)
        except Exception as e:
            logging.error(f"Error cleaning up request {req.request_id}: {e}")

    def close(self) -> None:
        """Close cache connection."""
        try:
            self.cache.close()
        except Exception as e:
            logging.error(f"Error closing cache: {e}")