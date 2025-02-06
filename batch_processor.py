import logging
import uuid
from pathlib import Path

from tqdm import tqdm

from api_client import MarkerClient
from cache_manager import CacheManager, ConversionRequest, Status
from common import ensure_directory
from pdf_splitter import chunk_pdf_to_temp


class BatchProcessor:
    """Handles processing of files, including chunking if needed."""

    def __init__(self, api_key: str, cache_dir: Path, chunk_size: int = 25):
        self.client = MarkerClient(api_key)
        self.cache = CacheManager(str(cache_dir))
        self.chunk_size = chunk_size  # pages per chunk for PDFs

    def should_chunk(self, file_path: Path) -> bool:
        """Determine if a file should be chunked."""
        return file_path.suffix.lower() == '.pdf'

    def process_file(
        self,
        file_path: Path,
        output_dir: Path,
        output_format: str = "markdown",
        **kwargs
    ) -> str:
        # Create temp directory for this conversion
        tmp_dir = Path("chunks") / f"{file_path.stem}_{uuid.uuid4().hex[:8]}"
        ensure_directory(tmp_dir)
        ensure_directory(output_dir)

        # Initialize request
        request = ConversionRequest(
                request_id=str(uuid.uuid4()),
                original_file=file_path,
                target_file=output_dir / file_path.name,
                output_format=output_format,
                status=Status.PENDING,
                tmp_dir=tmp_dir,
                chunk_size=self.chunk_size
            )

        try:
            # Handle PDF chunking
            if self.should_chunk(file_path):
                if chunk_result := chunk_pdf_to_temp(str(file_path), self.chunk_size, tmp_dir):
                    # Add additional chunks
                    for chunk_info in chunk_result.chunks:
                        request.add_chunk(Path(chunk_info.path), chunk_info.index)

            if len(request.chunks) == 0: # If no chunks created, add original file
                request.add_chunk(file_path, 0)

            # Submit all chunks to API
            logging.info(f"Submitting {len(request.chunks)} chunk(s) to API...")

            for chunk in tqdm(request.ordered_chunks, desc="Submitting to API", unit="chunk"):
                chunk_request_id = self.client.submit_file(chunk.path, output_format=output_format, **kwargs)
                if chunk_request_id:
                    chunk.mark_processing(chunk_request_id)
                else:
                    chunk.mark_failed(f"Failed to submit file {chunk.path}")
                    break

            # Update request status
            if request.has_failed:
                request.set_status(Status.FAILED)
            else:
                request.status = Status.PROCESSING

            self.cache.save(request)
            return request.request_id

        except Exception as e:
            request.status = Status.FAILED
            self.cache.save(request)
            logging.error(f"Error processing file {file_path}: {e}")
            return request.request_id

    def close(self) -> None:
        """Clean up resources."""
        self.cache.close()
