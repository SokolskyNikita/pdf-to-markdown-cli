import logging
import uuid
from pathlib import Path
from typing import Optional, List, Tuple, Dict

from docs_to_md.api.client import MarkerClient
from docs_to_md.api.models import (
    SUPPORTED_MIME_TYPES,
    ApiParams,
    SUPPORTED_INPUT_EXTENSIONS,
)
from docs_to_md.config.settings import Config
from docs_to_md.storage.cache import CacheManager
from docs_to_md.storage.models import ConversionRequest, Status
from docs_to_md.utils.exceptions import (
    FileError,
    PDFProcessingError,
    ConfigurationError,
)
from docs_to_md.utils.file_utils import FileDiscovery, TemporaryDirectory
from docs_to_md.utils.pdf_splitter import chunk_pdf_to_temp
from docs_to_md.utils.logging import ProgressTracker
from docs_to_md.core.result_handler import ResultHandler
from docs_to_md.core.paths import determine_output_paths, OutputPaths

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles processing of files, including chunking if needed."""

    def __init__(
        self,
        client: MarkerClient,
        cache: CacheManager,
        root_tmp_dir: Path,
        chunk_size: int,
    ):
        """
        Initialize the batch processor with shared client and cache.

        Args:
            client: Initialized MarkerClient instance.
            cache: Initialized CacheManager instance.
            root_tmp_dir: Base directory for temporary files.
            chunk_size: Pages per chunk for PDFs.
        """
        self.client = client
        self.cache = cache
        self.root_tmp_dir = root_tmp_dir
        self.chunk_size = chunk_size

    def should_chunk(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def process_file(
        self,
        file_path: Path,
        final_output_path: Path,
        api_params: ApiParams,
        output_paths_obj: OutputPaths,
    ) -> Optional[str]:
        """
        Process a single file: chunk if needed, submit to API.

        Args:
            file_path: Path to the input file.
            final_output_path: Path where the final output markdown file should be saved.
            api_params: Parameters for the Marker API call.
            output_paths_obj: The OutputPaths object containing final markdown and image paths.

        Returns:
            Request ID for tracking if submission is initiated, otherwise None.

        Raises:
            FileError: Potentially raised by underlying operations (though many are caught).
        """
        with TemporaryDirectory(self.root_tmp_dir, file_path.stem) as tmp_dir:
            request = ConversionRequest(
                request_id=str(uuid.uuid4()),
                original_file=file_path,
                target_file=final_output_path,
                output_format=api_params.output_format,
                status=Status.PENDING,
                tmp_dir=tmp_dir,
                chunk_size=self.chunk_size,
            )

            # Store the determined image dir in the request for the result handler
            request.images_dir = output_paths_obj.images_dir

            self.cache.save(request)

            try:
                if self.should_chunk(file_path):
                    try:
                        chunk_result = chunk_pdf_to_temp(
                            str(file_path), self.chunk_size, tmp_dir
                        )
                        if chunk_result:
                            for chunk_info in chunk_result.chunks:
                                request.add_chunk(
                                    Path(chunk_info.path), chunk_info.index
                                )
                            logger.debug(
                                f"Created {len(request.chunks)} chunks in {tmp_dir}"
                            )
                        else:
                            logger.debug(
                                f"No chunking needed for {file_path} (<= {self.chunk_size} pages)"
                            )
                    except (PDFProcessingError, Exception) as e:
                        logger.error(
                            f"Error chunking PDF {file_path}: {e}", exc_info=True
                        )
                        request.set_status(
                            Status.FAILED, f"Error chunking PDF: {str(e)}"
                        )
                        self.cache.save(request)
                        return request.request_id

                if not request.chunks:
                    request.add_chunk(file_path, 0)

                logger.info(
                    f"Submitting {len(request.chunks)} chunk(s) to API for {request.original_file.name}..."
                )

                submission_failed = False
                with ProgressTracker(
                    len(request.chunks), "Submitting to API", "chunk"
                ) as progress:
                    for chunk in request.ordered_chunks:
                        try:
                            chunk_request_id = self.client.submit_file(
                                chunk.path,
                                output_format=api_params.output_format,
                                langs=api_params.langs,
                                use_llm=api_params.use_llm,
                                strip_existing_ocr=api_params.strip_existing_ocr,
                                disable_image_extraction=api_params.disable_image_extraction,
                                force_ocr=api_params.force_ocr,
                                paginate=api_params.paginate,
                                max_pages=api_params.max_pages,
                            )
                            if chunk_request_id:
                                chunk.mark_processing(chunk_request_id)
                            else:
                                chunk.mark_failed(
                                    f"API submission failed for {chunk.path.name}"
                                )
                                submission_failed = True
                                break
                        except Exception as submit_e:
                            logger.error(
                                f"Unexpected error submitting chunk {chunk.path.name}: {submit_e}",
                                exc_info=True,
                            )
                            chunk.mark_failed(f"Error submitting chunk: {submit_e}")
                            submission_failed = True
                            break
                        finally:
                            progress.update()

                if submission_failed or request.has_failed:
                    request.set_status(
                        Status.FAILED,
                        request.error or "One or more chunk submissions failed.",
                    )
                    logger.error(
                        f"Submission failed for one or more chunks of {request.original_file.name}."
                    )
                else:
                    request.status = Status.PROCESSING
                    logger.info(
                        f"All chunks for {request.original_file.name} submitted successfully."
                    )

                self.cache.save(request)
                return request.request_id

            except Exception as e:
                error_msg = f"Error processing file {file_path}: {e}"
                logger.error(error_msg, exc_info=True)
                request.set_status(Status.FAILED, error_msg)
                self.cache.save(request)
                return request.request_id


class MarkerProcessor:
    """Handles the core business logic for processing files via Marker API."""

    def __init__(self, config: Config):
        """
        Initialize the processor with configuration.
        Sets up shared API client and cache manager.

        Args:
            config: Application configuration object.
        """
        self.config = config
        self.client = None
        self.cache = None
        try:
            self.client = MarkerClient(config.api_key)
            self.cache = CacheManager(config.cache_dir)
        except Exception as e:
            logger.critical(f"Failed to initialize core components: {e}", exc_info=True)
            raise ConfigurationError(f"Initialization failed: {e}") from e

    def _prepare_jobs(self) -> List[Tuple[Path, OutputPaths]]:
        jobs: List[Tuple[Path, OutputPaths]] = []
        input_path = Path(self.config.input_path)
        try:
            files_to_process = FileDiscovery.find_processable_files(
                input_path, SUPPORTED_MIME_TYPES, SUPPORTED_INPUT_EXTENSIONS
            )
        except FileError as fe:
            logger.error(f"Error finding processable files: {fe}")
            return []

        if not files_to_process:
            logger.warning(f"No processable files found in {input_path}")
            return []

        logger.debug(f"Prepared {len(files_to_process)} file(s) for processing.")
        for file_path in files_to_process:
            try:
                output_paths = determine_output_paths(
                    input_file=file_path,
                    output_dir_config=self.config.output_dir,
                    output_format=self.config.output_format,
                )
                jobs.append((file_path, output_paths))
            except (ValueError, FileError, OSError, Exception) as path_e:
                logger.error(
                    f"Error determining output paths for {file_path}: {path_e}. Skipping file."
                )

        return jobs

    def _submit_jobs(
        self, jobs: List[Tuple[Path, OutputPaths]]
    ) -> Dict[str, OutputPaths]:
        submitted_requests: Dict[str, OutputPaths] = {}

        if not jobs:
            return submitted_requests

        api_params = ApiParams(
            output_format=self.config.output_format,
            langs=self.config.langs,
            use_llm=self.config.use_llm,
            strip_existing_ocr=self.config.strip_existing_ocr,
            disable_image_extraction=self.config.disable_image_extraction,
            force_ocr=self.config.force_ocr,
            paginate=self.config.paginate,
            max_pages=self.config.max_pages,
        )

        logger.info(f"Starting submission process for {len(jobs)} job(s)...")
        batch_processor = BatchProcessor(
            self.client, self.cache, self.config.root_tmp_dir, self.config.chunk_size
        )

        for file_path, output_paths in jobs:
            logger.info(
                f"Submitting job: {file_path} -> {output_paths.markdown_path} (images: {output_paths.images_dir})"
            )
            try:
                request_id = batch_processor.process_file(
                    file_path=file_path,
                    final_output_path=output_paths.markdown_path,
                    api_params=api_params,
                    output_paths_obj=output_paths,
                )
                if request_id:
                    submitted_requests[request_id] = output_paths
                else:
                    logger.error(
                        f"Submission initiation failed for {file_path}, no request ID returned."
                    )

            except Exception as e:
                logger.error(
                    f"Failed to initiate processing for {file_path}: {e}", exc_info=True
                )

        logger.info(
            f"Submission process completed. Initiated {len(submitted_requests)} requests."
        )
        return submitted_requests

    def _process_results(self, submitted_requests: Dict[str, OutputPaths]) -> None:
        if not submitted_requests:
            logger.info(
                "No requests were successfully submitted, skipping result processing."
            )
            return

        logger.debug(
            f"Starting result processing for {len(submitted_requests)} submitted request(s)..."
        )
        request_ids_to_process = list(submitted_requests.keys())

        result_handler = ResultHandler(self.client, self.cache, self.config)
        try:
            result_handler.process_cache_items(request_ids_to_process)
        except Exception as e:
            logger.error(f"Error during result processing phase: {e}", exc_info=True)

    def process(self) -> None:
        if not self.client or not self.cache:
            logger.critical(
                "Processor not initialized correctly (client or cache missing). Aborting."
            )
            return

        try:
            logger.debug("Starting processing workflow...")
            jobs_to_run = self._prepare_jobs()

            if not jobs_to_run:
                logger.info("No jobs to run. Exiting workflow.")
                return

            submitted_requests = self._submit_jobs(jobs_to_run)

            self._process_results(submitted_requests)

            logger.info("Processing workflow finished.")

        except Exception as e:
            logger.critical(
                f"Critical error during main processing workflow: {e}", exc_info=True
            )
            raise FileError(f"Processing workflow failed: {e}") from e
        finally:
            if self.cache:
                try:
                    logger.debug("Closing cache manager.")
                    self.cache.close()
                except Exception as ce:
                    logger.error(f"Error closing cache manager: {ce}", exc_info=False)
