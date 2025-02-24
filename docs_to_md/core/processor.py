import logging
import uuid
from pathlib import Path

from docs_to_md.api.client import MarkerClient
from docs_to_md.api.models import SUPPORTED_MIME_TYPES, ApiParams
from docs_to_md.config.settings import Config
from docs_to_md.pdf.splitter import chunk_pdf_to_temp
from docs_to_md.storage.cache import CacheManager
from docs_to_md.storage.models import ConversionRequest, Status
from docs_to_md.utils.exceptions import FileError, PDFProcessingError
from docs_to_md.utils.file_utils import FileDiscovery, TemporaryDirectory, ensure_directory
from docs_to_md.utils.logging import ProgressTracker
from docs_to_md.core.result_handler import ResultHandler

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles processing of files, including chunking if needed."""

    def __init__(self, api_key: str, cache_dir: Path, chunk_size: int = 25):
        """
        Initialize the batch processor.
        
        Args:
            api_key: API key for authentication
            cache_dir: Directory for caching
            chunk_size: Pages per chunk for PDFs
        """
        self.client = MarkerClient(api_key)
        self.cache = CacheManager(str(cache_dir))
        self.chunk_size = chunk_size  # pages per chunk for PDFs

    def should_chunk(self, file_path: Path) -> bool:
        """
        Determine if a file should be chunked.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be chunked, False otherwise
        """
        return file_path.suffix.lower() == '.pdf'

    def process_file(
        self,
        file_path: Path,
        output_dir: Path,
        api_params: ApiParams
    ) -> str:
        """
        Process a single file.
        
        Args:
            file_path: Path to file
            output_dir: Output directory
            api_params: Parameters for the API call
            
        Returns:
            Request ID for tracking
            
        Raises:
            FileError: If file processing fails
        """
        # Create temp directory for this conversion
        with TemporaryDirectory(Path("chunks"), file_path.stem) as tmp_dir:
            ensure_directory(output_dir)
            
            # Initialize request
            request = ConversionRequest(
                request_id=str(uuid.uuid4()),
                original_file=file_path,
                target_file=output_dir / file_path.name,
                output_format=api_params.output_format,
                status=Status.PENDING,
                tmp_dir=tmp_dir,
                chunk_size=self.chunk_size
            )
            
            # Save request early for tracking
            self.cache.save(request)

            try:
                # Handle PDF chunking
                if self.should_chunk(file_path):
                    try:
                        chunk_result = chunk_pdf_to_temp(str(file_path), self.chunk_size, tmp_dir)
                        if chunk_result:
                            # Add additional chunks
                            for chunk_info in chunk_result.chunks:
                                request.add_chunk(Path(chunk_info.path), chunk_info.index)
                    except (PDFProcessingError, Exception) as e:
                        logger.error(f"Error chunking PDF {file_path}: {e}")
                        request.set_status(Status.FAILED, f"Error chunking PDF: {str(e)}")
                        self.cache.save(request)
                        return request.request_id

                if len(request.chunks) == 0:  # If no chunks created, add original file
                    request.add_chunk(file_path, 0)

                # Submit all chunks to API
                logger.info(f"Submitting {len(request.chunks)} chunk(s) to API...")
                
                progress = ProgressTracker(len(request.chunks), "Submitting to API", "chunk")
                
                for chunk in request.ordered_chunks:
                    chunk_request_id = self.client.submit_file(
                        chunk.path, 
                        output_format=api_params.output_format,
                        langs=api_params.langs,
                        use_llm=api_params.use_llm,
                        strip_existing_ocr=api_params.strip_existing_ocr,
                        disable_image_extraction=api_params.disable_image_extraction,
                        force_ocr=api_params.force_ocr,
                        paginate=api_params.paginate,
                        max_pages=api_params.max_pages
                    )
                    if chunk_request_id:
                        chunk.mark_processing(chunk_request_id)
                    else:
                        chunk.mark_failed(f"Failed to submit file {chunk.path}")
                        break
                        
                    progress.update()
                
                progress.close()

                # Update request status
                if request.has_failed:
                    request.set_status(Status.FAILED)
                else:
                    request.status = Status.PROCESSING

                self.cache.save(request)
                return request.request_id

            except Exception as e:
                request.status = Status.FAILED
                request.error = str(e)
                self.cache.save(request)
                logger.error(f"Error processing file {file_path}: {e}")
                return request.request_id

    def close(self) -> None:
        """Clean up resources."""
        self.cache.close()
        
    def __enter__(self):
        """Support for context manager."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.close()


class MarkerProcessor:
    """Handles the core business logic for processing PDFs."""

    def __init__(self, config: Config):
        """
        Initialize the processor with configuration.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.config.ensure_directories()

    def process(self) -> None:
        """
        Process files according to configuration.
        
        Raises:
            FileError: If file processing fails
        """
        # Initialize processors
        with BatchProcessor(self.config.api_key, self.config.cache_dir, chunk_size=self.config.chunk_size) as batch_processor, \
             ResultHandler(self.config.api_key, self.config.cache_dir) as result_handler:

            try:
                # Process input path
                input_path = Path(self.config.input_path)
                
                # Find processable files
                supported_extensions = ['.pdf', '.docx', '.doc', '.pptx', '.ppt', 
                                      '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff']
                                      
                files_to_process = FileDiscovery.find_processable_files(
                    input_path, 
                    SUPPORTED_MIME_TYPES,
                    supported_extensions
                )

                if not files_to_process:
                    logger.warning(f"No processable files found in {input_path}")
                    return

                # Create ApiParams from config
                api_params = ApiParams(
                    output_format=self.config.output_format,
                    langs=self.config.langs,
                    use_llm=self.config.use_llm,
                    strip_existing_ocr=self.config.strip_existing_ocr,
                    disable_image_extraction=self.config.disable_image_extraction,
                    force_ocr=self.config.force_ocr,
                    paginate=self.config.paginate,
                    max_pages=self.config.max_pages
                )

                # Process each file
                for file_path in files_to_process:
                    logger.info(f"Processing {file_path}")
                    batch_processor.process_file(
                        file_path=file_path,
                        output_dir=self.config.output_dir,
                        api_params=api_params
                    )

                # Process results
                result_handler.process_cache_items()

                logger.info("All processing completed successfully.")
                
            except Exception as e:
                logger.error(f"Error during processing: {e}")
                raise FileError(f"Processing failed: {e}") 