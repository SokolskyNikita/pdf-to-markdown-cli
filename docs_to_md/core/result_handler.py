import base64
import json
import logging
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from docs_to_md.api.client import MarkerClient
from docs_to_md.api.models import MarkerStatus, StatusEnum
from docs_to_md.storage.cache import CacheManager
from docs_to_md.storage.models import ChunkInfo, ConversionRequest, Status
from docs_to_md.utils.exceptions import ResultProcessingError
from docs_to_md.utils.file_utils import FileIO, ensure_directory, safe_delete
from docs_to_md.utils.logging import ProgressTracker

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles processing and transformation of images extracted from documents."""
    
    def transform_image_name(self, original_name: str, chunk: ChunkInfo, 
                           chunk_size: int) -> Tuple[str, str]:
        """
        Transform image name and return new names for file and markdown.
        
        Args:
            original_name: Original image name from API
            chunk: Chunk info for context
            chunk_size: Number of pages per chunk
            
        Returns:
            Tuple of (new_filename, markdown_reference_name)
        """
        base_page_num = (chunk.index * chunk_size) + 1
        
        # Extract file extension properly
        parts = original_name.split('.')
        extension = ""
        if len(parts) > 1:
            extension = f".{parts[-1].lower()}"
            # Validate extension is a common image type
            if extension not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff']:
                extension = ".jpg"  # Default to jpg if unknown
        else:
            extension = ".jpg"  # Default extension
        
        # Try to extract page and figure numbers with more robust patterns
        page_match = re.search(r'(?:_|-)page(?:_|-)?(\d+)', original_name, re.IGNORECASE)
        figure_match = re.search(r'(?:_|-)(?:figure|fig)(?:_|-)?(\d+)', original_name, re.IGNORECASE)
        
        if page_match and figure_match:
            # Calculate new page number based on chunk position
            page_num = int(page_match.group(1))
            corrected_page_num = base_page_num + page_num - 1  # -1 because pages often start at 1
            figure_num = int(figure_match.group(1))
            
            # Generate new filename with corrected page number
            new_name = f"page_{corrected_page_num}_figure_{figure_num}{extension}"
            return new_name, new_name
        else:
            # Fallback: use chunk number, timestamp, and random identifier for uniqueness
            timestamp = datetime.now().strftime("%H%M%S")
            random_suffix = uuid.uuid4().hex[:6]
            fallback_name = f"chunk_{chunk.index}_img_{timestamp}_{random_suffix}{extension}"
            return fallback_name, fallback_name
    
    def process_images(self, images: Dict[str, str], chunk: ChunkInfo, 
                     tmp_dir: Path, chunk_size: int) -> Dict[str, str]:
        """
        Process images from API response.
        
        Args:
            images: Dictionary of image names to base64 content
            chunk: Chunk info for context
            tmp_dir: Temporary directory for storage
            chunk_size: Number of pages per chunk
            
        Returns:
            Dictionary mapping original image names to new image references
        """
        if not images:
            return {}
            
        # Prepare images directory
        images_dir = tmp_dir / "images"
        ensure_directory(images_dir)
        
        # Process each image
        image_map = {}
        for original_name, b64_content in images.items():
            # Transform name
            new_name, markdown_name = self.transform_image_name(original_name, chunk, chunk_size)
            
            # Save image
            try:
                image_data = base64.b64decode(b64_content)
                (images_dir / new_name).write_bytes(image_data)
                
                # Map original name to new markdown reference
                image_map[original_name] = f"images/{markdown_name}"
            except Exception as e:
                logger.error(f"Failed to save image {original_name} to {new_name}: {e}")
                
        return image_map


class ResultSaver:
    """Handles saving and combining results."""
    
    def __init__(self):
        """Initialize the result saver."""
        self.format_extensions = {
            "markdown": ".md",
            "json": ".json",
            "html": ".html",
            "txt": ".txt"  # default
        }
    
    def save_content(self, content: str, path: Path) -> None:
        """
        Save content to file, ensuring parent directory exists.
        
        Args:
            content: Content to save
            path: Path to save to
            
        Raises:
            ResultProcessingError: If save fails
        """
        try:
            FileIO.write_file(path, content)
        except Exception as e:
            raise ResultProcessingError(f"Failed to save content to {path}: {e}")
    
    def get_output_directory(self, req: ConversionRequest) -> Path:
        """
        Create and return output directory with timestamp.
        
        Args:
            req: Conversion request
            
        Returns:
            Path to output directory
        """
        timestamp = datetime.now().strftime("%y-%m-%d_%H-%M")
        base_dir = Path("converted")
        output_dir = base_dir / req.original_file.stem / timestamp
        ensure_directory(output_dir)
        return output_dir
    
    def combine_results(self, req: ConversionRequest) -> Tuple[Path, int]:
        """
        Combine chunk results into a single output file.
        
        Args:
            req: Conversion request with chunks
            
        Returns:
            Tuple of (output_file_path, total_size)
            
        Raises:
            ResultProcessingError: If combination fails
        """
        # Create output directory
        output_dir = self.get_output_directory(req)
        output_file = output_dir / f"{req.original_file.name}{self.format_extensions.get(req.output_format, '.txt')}"
        
        # Ensure output directory exists
        ensure_directory(output_file.parent)
        
        try:
            # Write chunks to output file one at a time to minimize memory usage
            total_size = 0
            with open(output_file, 'w', encoding='utf-8') as outf:
                for i, chunk in enumerate(req.ordered_chunks):
                    result_path = chunk.get_result_path(req.tmp_dir)
                    if not result_path.exists():
                        raise ResultProcessingError(f"Result file does not exist: {result_path}")
                    
                    # Read and write chunk content in blocks
                    with open(result_path, 'r', encoding='utf-8') as infile:
                        # Copy content in blocks
                        while True:
                            block = infile.read(65536)  # Read 64KB at a time
                            if not block:
                                break
                            outf.write(block)
                            total_size += len(block)
                        
                        # Add separator between chunks, but not after the last one
                        if i < len(req.ordered_chunks) - 1:
                            outf.write("\n\n")
                            total_size += 2
            
            # Verify file was written successfully
            if total_size == 0:
                safe_delete(output_file)  # Clean up empty file
                raise ResultProcessingError("Combined content is empty")
                
            return output_file, total_size
            
        except Exception as e:
            # Clean up partial file on error
            if output_file.exists():
                safe_delete(output_file)
                
            if isinstance(e, ResultProcessingError):
                raise
            raise ResultProcessingError(f"Failed to combine results: {str(e)}")
            
    def move_images(self, source_dir: Path, target_dir: Path) -> None:
        """
        Move images from source to target directory.
        
        Args:
            source_dir: Source images directory
            target_dir: Target images directory
            
        Raises:
            ResultProcessingError: If image move fails
        """
        if not source_dir.exists():
            return
            
        try:
            # Ensure target directory exists
            target_images_dir = target_dir / "images"
            if target_images_dir.exists():
                safe_delete(target_images_dir)
                
            # Copy images directory
            try:
                shutil.copytree(source_dir, target_images_dir)
                safe_delete(source_dir)  # Clean up after successful copy
                logger.info(f"Moved images to {target_dir}/images/")
            except Exception as e:
                logger.warning(f"Could not copy images directory: {e}. Trying to copy files...")
                ensure_directory(target_images_dir)
                for img_file in source_dir.glob("*"):
                    try:
                        shutil.copy2(img_file, target_images_dir / img_file.name)
                    except Exception as copy_e:
                        logger.error(f"Failed to copy image {img_file}: {copy_e}")
        except Exception as e:
            raise ResultProcessingError(f"Failed to move images: {e}")


class ResultHandler:
    """Handles processing of conversion results."""
    
    def __init__(self, api_key: str, cache_dir: Path, check_interval: int = 15):
        """
        Initialize the result handler.
        
        Args:
            api_key: API key for authentication
            cache_dir: Directory for cache
            check_interval: Interval between API status checks
        """
        self.client = MarkerClient(api_key)
        self.cache = CacheManager(str(cache_dir))
        self.check_interval = check_interval
        self.saver = ResultSaver()
        self.image_processor = ImageProcessor()

    def process_cache_items(self) -> None:
        """
        Process all pending items in the cache.
        
        This is the main method to process results from the API.
        """
        reqs = self.cache.get_all()
        if not reqs:
            return

        progress = ProgressTracker(len(reqs), "Processing requests")
        
        for req in reqs:
            try:
                # Skip already completed or failed requests
                if req.status in (Status.FAILED, Status.COMPLETE):
                    self._cleanup_request(req)
                    progress.update()
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
                    
                progress.update()
                
            except Exception as e:
                logger.error(f"Error processing request {req.request_id}: {e}")
                req.set_status(Status.FAILED, str(e))
                self._cleanup_request(req)
                
        progress.close()

    def _process_pending_chunks(self, req: ConversionRequest, chunks: List[ChunkInfo]) -> None:
        """
        Process pending chunks.
        
        Args:
            req: Conversion request
            chunks: List of pending chunks
        """
        logger.info(f"Processing {len(chunks)} chunks for {req.original_file.name}")
        
        progress = ProgressTracker(len(chunks), "Processing chunks")
        
        for chunk in chunks:
            if self._process_chunk(chunk, req):
                req.set_status(Status.FAILED, chunk.error)
                break
                
            progress.update()
            
        progress.close()
        
        # Save updated request
        self.cache.save(req)

    def _process_chunk(self, chunk: ChunkInfo, req: ConversionRequest) -> bool:
        """
        Process a single chunk.
        
        Args:
            chunk: Chunk to process
            req: Parent conversion request
            
        Returns:
            True if processing should stop (failure), False otherwise
        """
        if not req.tmp_dir:
            chunk.mark_failed("No temporary directory set for request")
            return True

        max_retries = 20  # Maximum number of retries (5 minutes with 15 seconds interval)
        retry_count = 0
        
        while retry_count < max_retries:
            status = self.client.check_status(chunk.request_id)
            
            # Add None check before accessing status attributes
            if status is None:
                retry_count += 1
                if retry_count >= max_retries:
                    chunk.mark_failed("Failed to retrieve status from API after multiple attempts")
                    return True
                logger.warning(f"Received None status for chunk {chunk.request_id}, retrying...")
                time.sleep(self.check_interval)
                continue
                
            match status.status:
                case StatusEnum.FAILED:
                    chunk.mark_failed(status.error or "Unknown API error")
                    return True
                    
                case StatusEnum.COMPLETE:
                    try:
                        self._save_chunk_result(chunk, status, req)
                        return False
                    except Exception as e:
                        chunk.mark_failed(str(e))
                        return True
                        
                case _:
                    retry_count += 1
                    if retry_count >= max_retries:
                        chunk.mark_failed(f"API processing timed out after {max_retries * self.check_interval} seconds")
                        return True
                    time.sleep(self.check_interval)
        
        # This line should never be reached due to the return inside the loop
        chunk.mark_failed("Unexpected error processing chunk")
        return True

    def _save_chunk_result(self, chunk: ChunkInfo, status: MarkerStatus, req: ConversionRequest) -> None:
        """
        Save chunk result to temporary storage.
        
        Args:
            chunk: Chunk being processed
            status: API status response
            req: Parent conversion request
            
        Raises:
            ResultProcessingError: If saving fails
        """
        content = None

        # Get content from appropriate field based on output format
        if status.markdown is not None:
            content = status.markdown
        elif status.json_data is not None:
            content = json.dumps(status.json_data)

        if not content:
            logger.error(f"No content found in result for chunk {chunk.path}")
            raise ResultProcessingError("No content in result")

        # Save content to temp file in request's tmp_dir
        temp_file = chunk.get_result_path(req.tmp_dir)
        
        # Process images if present
        image_map = {}
        if status.images:
            image_map = self.image_processor.process_images(
                status.images, chunk, req.tmp_dir, req.chunk_size
            )
            
            # Update image references in content
            for original_name, new_ref in image_map.items():
                content = content.replace(f"]({original_name})", f"]({new_ref})")

        logger.info(f"Saving chunk result to {temp_file}")
        self.saver.save_content(content, temp_file)
        chunk.mark_complete()

    def _combine_and_save_result(self, req: ConversionRequest) -> None:
        """
        Combine results from all chunks and save final output.
        
        Args:
            req: Conversion request
            
        Raises:
            ResultProcessingError: If combination fails
        """
        try:
            # Combine chunks and get output file
            output_file, total_size = self.saver.combine_results(req)
            logger.info(f"Successfully saved output to {output_file} ({total_size} bytes)")

            # Move images directory if it exists
            images_dir = req.tmp_dir / "images"
            if images_dir.exists():
                self.saver.move_images(images_dir, output_file.parent)

            req.set_status(Status.COMPLETE)
            
            # Save final status to cache
            self.cache.save(req)
            
        except Exception as e:
            error_msg = f"Failed to combine results: {str(e)}"
            logger.error(error_msg)
            req.set_status(Status.FAILED, error_msg)
            self.cache.save(req)
            raise

    def _cleanup_request(self, req: ConversionRequest) -> None:
        """
        Clean up resources for a request.
        
        Args:
            req: Request to clean up
        """
        try:
            # Clean up temp directory if it exists
            if req.tmp_dir and Path(req.tmp_dir).exists():
                safe_delete(req.tmp_dir)

            # Remove from cache
            self.cache.delete(req.request_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up request {req.request_id}: {e}")

    def close(self) -> None:
        """Close connections and free resources."""
        try:
            self.cache.close()
        except Exception as e:
            logger.error(f"Error closing cache: {e}")
            
    def __enter__(self):
        """Support for context manager."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.close() 