import base64
import binascii
import json
import logging
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from docs_to_md.api.client import MarkerClient
from docs_to_md.api.models import MarkerStatus, StatusEnum, SUPPORTED_IMAGE_EXTENSIONS
from docs_to_md.config.settings import Config
from docs_to_md.storage.cache import CacheManager
from docs_to_md.storage.models import ChunkInfo, ConversionRequest, Status
from docs_to_md.utils.exceptions import ResultProcessingError
from docs_to_md.utils.file_utils import FileIO, ensure_directory, safe_delete
from docs_to_md.utils.logging import ProgressTracker

logger = logging.getLogger(__name__)

# Exponential backoff settings for per-chunk polling
CHUNK_RETRY_BACKOFF_FACTOR = 2
CHUNK_RETRY_INITIAL_DELAY_SECONDS = 5
CHUNK_RETRY_MAX_ATTEMPTS = 8
CHUNK_RETRY_MAX_DELAY_SECONDS = 60


class ResultSaver:
    """Handles saving combined results and moving assets."""

    def save_content(self, content: str, path: Path) -> None:
        try:
            ensure_directory(path.parent)
            FileIO.write_file(path, content)
        except Exception as e:
            raise ResultProcessingError(f"Failed to save content to {path}: {e}") from e

    def combine_results(self, req: ConversionRequest) -> Tuple[Path, int]:
        output_file = req.target_file
        if not output_file:
            raise ResultProcessingError(
                f"Target file path not set for request {req.request_id}"
            )
        if not req.tmp_dir:
            raise ResultProcessingError(
                f"Temporary directory not set for request {req.request_id}"
            )

        logger.debug(
            f"Combining {len(req.ordered_chunks)} chunk results into {output_file}..."
            if req.ordered_chunks
            else f"Processing single result for {output_file}..."
        )
        total_size = 0
        try:
            with open(output_file, "w", encoding="utf-8") as outf:
                if not req.ordered_chunks:
                    logger.warning(
                        f"No chunks found for request {req.request_id}, cannot combine. Target file may be empty."
                    )
                    return output_file, 0

                for i, chunk in enumerate(req.ordered_chunks):
                    result_path = chunk.get_result_path(req.tmp_dir)
                    if not result_path.exists():
                        raise ResultProcessingError(
                            f"Result file for chunk {i} ({result_path.name}) not found in {req.tmp_dir}"
                        )

                    logger.debug(
                        f"Appending chunk {i+1}/{len(req.ordered_chunks)} from {result_path.name}"
                    )
                    with open(result_path, "r", encoding="utf-8") as infile:
                        shutil.copyfileobj(infile, outf, length=65536)
                        total_size += result_path.stat().st_size

                    if i < len(req.ordered_chunks) - 1:
                        outf.write("\n\n")
                        total_size += 2  # Account for separator bytes

            final_size = output_file.stat().st_size
            logger.debug(
                f"Successfully combined results to {output_file} (Final size: {final_size} bytes)"
            )
            if req.images_dir and req.tmp_dir:
                source_images_dir = req.tmp_dir / "images"
                if source_images_dir.exists():
                    ensure_directory(req.images_dir)
                    logger.debug(f"Created images directory {req.images_dir} (images will be moved)")
                else:
                    logger.debug(f"No images found - skipping creation of {req.images_dir}")
            return output_file, final_size

        except Exception as e:
            if output_file.exists():
                logger.error(
                    f"Error during result combination for {output_file}. Deleting partial file."
                )
                safe_delete(output_file)

            if isinstance(e, ResultProcessingError):
                raise
            raise ResultProcessingError(
                f"Failed to combine results into {output_file}: {str(e)}"
            ) from e

    def move_images(self, source_images_dir: Path, target_images_dir: Path) -> None:
        if not source_images_dir.exists():
            logger.debug(
                f"Source images directory {source_images_dir} not found, nothing to move."
            )
            return

        logger.debug(
            f"Moving/Copying images from {source_images_dir} to {target_images_dir}..."
        )

        try:
            shutil.copytree(source_images_dir, target_images_dir, dirs_exist_ok=True)
            logger.debug(
                f"Successfully copied images tree to {target_images_dir}. Source temp directory will be cleaned up later."
            )

        except Exception as e:
            raise ResultProcessingError(
                f"Failed to move images to {target_images_dir}: {e}"
            ) from e


class ResultHandler:
    """Handles polling for API results, combining them, moving assets, and cleanup."""

    def __init__(
        self,
        client: MarkerClient,
        cache: CacheManager,
        config: Config,
        check_interval: int = 15,
    ):
        self.client = client
        self.cache = cache
        self.config = config
        self.check_interval = check_interval
        self.saver = ResultSaver()

    def _transform_image_name(
        self, original_name: str, chunk: ChunkInfo, chunk_size: int
    ) -> str:
        base_page_num = (chunk.index * chunk_size) + 1
        extension = "jpg"
        parts = original_name.split(".")
        if len(parts) > 1:
            image_extension = parts[-1].lower()
            if image_extension in SUPPORTED_IMAGE_EXTENSIONS:
                extension = image_extension

        page_match = re.search(
            r"(?:_|-)page(?:_|-)?(\d+)", original_name, re.IGNORECASE
        )
        figure_match = re.search(
            r"(?:_|-)(?:figure|fig)(?:_|-)?(\d+)", original_name, re.IGNORECASE
        )

        if page_match and figure_match:
            try:
                page_num = int(page_match.group(1))
                figure_num = int(figure_match.group(1))
                corrected_page_num = base_page_num + page_num - 1
                markdown_name = (
                    f"page_{corrected_page_num}_figure_{figure_num}.{extension}"
                )
                return markdown_name
            except ValueError:
                logger.warning(
                    f"Could not parse page/figure numbers from {original_name}"
                )

        timestamp = datetime.now().strftime("%H%M%S")
        random_suffix = uuid.uuid4().hex[:6]
        fallback_name = (
            f"chunk_{chunk.index}_img_{timestamp}_{random_suffix}.{extension}"
        )
        logger.debug(
            f"Using fallback name {fallback_name} for original image {original_name}"
        )
        return fallback_name

    def _process_chunk_images(
        self, images: Dict[str, str], chunk: ChunkInfo, tmp_dir: Path, chunk_size: int, final_images_dir: Path
    ) -> Dict[str, str]:
        if not images or not isinstance(images, dict):
            return {}

        temp_images_dir = tmp_dir / "images"
        ensure_directory(temp_images_dir)
        image_map = {}
        logger.debug(
            f"Processing {len(images)} image(s) for chunk {chunk.index} into {temp_images_dir}"
        )

        final_images_dir_name = final_images_dir.name

        for original_name, b64_content in images.items():
            markdown_name = self._transform_image_name(original_name, chunk, chunk_size)
            # Save to the temporary image directory first
            image_file_path = temp_images_dir / markdown_name
            try:
                image_data = base64.b64decode(b64_content)
                image_file_path.write_bytes(image_data)
                image_map[original_name] = f"{final_images_dir_name}/{markdown_name}"
            except (ValueError, binascii.Error) as b64_err:
                logger.error(
                    f"Failed to decode base64 for image '{original_name}' in chunk {chunk.index}: {b64_err}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to save image {original_name} to {image_file_path}: {e}"
                )
        return image_map

    def process_cache_items(self, request_ids: List[str]) -> None:
        if not request_ids:
            logger.info("No request IDs provided for result processing; nothing to do.")
            return

        # Keep looping until all tracked requests reach a terminal state or
        # disappear from the cache (cleanup).
        remaining_ids = list(request_ids)
        pass_count = 0

        while remaining_ids:
            reqs_to_process: List[ConversionRequest] = []

            # Reload current state for all remaining requests
            for req_id in list(remaining_ids):
                req = self.cache.get(req_id)
                if not req:
                    logger.debug(
                        f"Request {req_id} no longer in cache; assuming it was cleaned up."
                    )
                    remaining_ids.remove(req_id)
                    continue

                if not req.target_file:
                    logger.error(
                        f"Missing target_file path in cached request {req_id}. Skipping."
                    )
                    remaining_ids.remove(req_id)
                    continue

                if req.status in (Status.FAILED, Status.COMPLETE):
                    # Ensure cleanup runs for terminal requests that might have been
                    # left in the cache from a previous run.
                    self._handle_single_request(req)
                    remaining_ids.remove(req_id)
                    continue

                reqs_to_process.append(req)

            if not reqs_to_process:
                # Nothing left that is valid and non-terminal
                break

            pass_count += 1
            total_pending = sum(len(req.pending_chunks) for req in reqs_to_process)
            total_complete = sum(
                len([c for c in req.chunks if c.status == Status.COMPLETE])
                for req in reqs_to_process
            )
            logger.info(
                f"Pass {pass_count}: {len(reqs_to_process)} active request(s); "
                f"{total_pending} pending chunk(s), {total_complete} complete chunk(s)."
            )
            with ProgressTracker(
                len(reqs_to_process), "Processing requests"
            ) as progress:
                for req in reqs_to_process:
                    self._handle_single_request(req)
                    progress.update()
            logger.info(
                f"Finished processing pass {pass_count} for active requests."
            )

            # Re-check if any requests remain after this pass
            still_active = []
            for req_id in remaining_ids:
                req = self.cache.get(req_id)
                if req and req.status not in (Status.FAILED, Status.COMPLETE):
                    still_active.append(req_id)
            remaining_ids = still_active

            if not remaining_ids:
                break

            # Recompute earliest retry target after handling this pass, so sleep
            # respects freshly updated per-chunk backoff state.
            next_retry_at: float | None = None
            for req_id in remaining_ids:
                req = self.cache.get(req_id)
                if not req:
                    continue
                for chunk in req.pending_chunks:
                    if chunk.retry_after is not None and (
                        next_retry_at is None or chunk.retry_after < next_retry_at
                    ):
                        next_retry_at = chunk.retry_after

            # Determine how long to sleep before the next pass, based on the soonest
            # per-chunk retry time. The actual retry timings are controlled solely
            # by `_schedule_next_chunk_check`, via each chunk's `retry_after`.
            sleep_for: float = self.check_interval
            now = time.time()
            if next_retry_at is not None and next_retry_at > now:
                sleep_for = max(0.0, next_retry_at - now)

            if sleep_for > 0:
                logger.info(
                    f"Active requests remain after pass {pass_count}; sleeping "
                    f"{sleep_for:.2f}s before next status check."
                )
                time.sleep(sleep_for)

        logger.info(
            f"Result processing complete after {pass_count} pass(es); "
            "all tracked requests are now in a terminal state or have been cleaned up."
        )

    def _handle_single_request(self, req: ConversionRequest) -> None:
        logger.debug(
            f"Handling request {req.request_id} for {req.original_file.name} "
            f"(status={req.status}, pending_chunks={len(req.pending_chunks)})"
        )
        try:
            if req.status in (Status.FAILED, Status.COMPLETE):
                logger.debug(
                    f"Request {req.request_id} already in terminal state ({req.status}). Cleaning up."
                )
                self._cleanup_request(req)
                return

            if pending_chunks := req.pending_chunks:
                logger.debug(
                    f"Request {req.request_id} has {len(pending_chunks)} pending chunk(s). Checking status..."
                    if pending_chunks
                    else f"Request {req.request_id} has no pending chunks."
                )
                self._poll_and_save_pending_chunks(req, pending_chunks)

            # Re-fetch request state after polling
            updated_req = self.cache.get(req.request_id)
            if not updated_req:
                logger.error(
                    f"Request {req.request_id} disappeared from cache during processing. Cannot proceed."
                )
                return
            req = updated_req

            if req.all_complete:
                logger.debug(
                    f"All chunks complete for {req.request_id}. Combining results..."
                    if req.chunks
                    else f"Processing complete for single-file request {req.request_id}. Saving result..."
                )
                self._combine_and_save_result(req)
                self._move_final_images(req)
                self._cleanup_request(req)
                logger.info(
                    f"Converted {req.original_file.name} into {req.target_file.name}, image folder {req.images_dir}."
                )
            elif req.has_failed:
                logger.error(
                    f"One or more chunks failed for request {req.request_id}. Cleaning up."
                )
                self._cleanup_request(req)
            else:
                logger.debug(
                    f"Request {req.request_id} still processing after check; it will be revisited in a later polling cycle."
                )
                self.cache.save(req)

        except Exception as e:
            logger.error(
                f"Unexpected error handling request {req.request_id}: {e}",
                exc_info=True,
            )
            try:
                req.set_status(Status.FAILED, f"Handler error: {str(e)}")
                self.cache.save(req)
                self._cleanup_request(req)
            except Exception as cleanup_e:
                logger.error(
                    f"Further error during error handling/cleanup for {req.request_id}: {cleanup_e}"
                )

    def _poll_and_save_pending_chunks(
        self, req: ConversionRequest, chunks: List[ChunkInfo]
    ) -> None:
        if not chunks:
            return
        logger.info(
            f"Polling status for request {req.request_id}: "
            f"{len([c for c in chunks if c.retry_after is None or c.retry_after <= time.time()])} "
            f"ready chunk(s), {len(chunks)} total pending."
        )
        now = time.time()

        with ProgressTracker(len(chunks), "Checking chunk status") as progress:
            for chunk in chunks:
                if chunk.retry_after is not None and now < chunk.retry_after:
                    progress.update()
                    continue

                if self._poll_and_process_single_chunk(
                    chunk, req
                ):  # Returns True if chunk failed
                    logger.error(
                        f"Chunk {chunk.index} (ID: {chunk.request_id}) failed for request {req.request_id}. Error: {chunk.error}"
                    )
                    req.set_status(
                        Status.FAILED, chunk.error or "A chunk failed processing."
                    )
                else:
                    logger.debug(
                        f"Chunk {chunk.index} (ID: {chunk.request_id}) processed successfully or still pending."
                    )
                progress.update()
        self.cache.save(req)

    def _schedule_next_chunk_check(self, chunk: ChunkInfo) -> None:
        attempts = max(chunk.retry_attempts, 0)
        effective_attempt = min(attempts, max(CHUNK_RETRY_MAX_ATTEMPTS - 1, 0))
        delay = CHUNK_RETRY_INITIAL_DELAY_SECONDS * (
            CHUNK_RETRY_BACKOFF_FACTOR ** effective_attempt
        )
        if delay > CHUNK_RETRY_MAX_DELAY_SECONDS:
            delay = CHUNK_RETRY_MAX_DELAY_SECONDS

        chunk.retry_attempts = attempts + 1
        chunk.retry_after = time.time() + delay

    def _poll_and_process_single_chunk(
        self, chunk: ChunkInfo, req: ConversionRequest
    ) -> bool:
        """Poll API status for one chunk and save the result if complete.

        Per-chunk exponential backoff is handled via `retry_attempts` and
        `retry_after` on `ChunkInfo`, so this method performs a single status
        check and schedules the next one when needed.
        """
        if chunk.status != Status.PROCESSING:
            logger.warning(
                f"Attempting to process chunk {chunk.index} not in PROCESSING state ({chunk.status}) for request {req.request_id}"
            )
            return chunk.status == Status.FAILED

        if not req.tmp_dir or not chunk.request_id:
            error_msg = (
                f"Invalid state for processing chunk {chunk.index} (req_id: {req.request_id}): "
                f"Missing tmp_dir or chunk.request_id."
            )
            logger.error(error_msg)
            chunk.mark_failed(error_msg)
            return True

        # Enforce a hard cap on polling attempts for this chunk.
        if chunk.retry_attempts >= CHUNK_RETRY_MAX_ATTEMPTS:
            msg = (
                f"Chunk {chunk.request_id} did not complete after "
                f"{CHUNK_RETRY_MAX_ATTEMPTS} polling attempts; marking as failed."
            )
            logger.error(msg)
            chunk.mark_failed(msg)
            return True

        status: MarkerStatus | None = self.client.check_status(chunk.request_id)

        if status is None:
            logger.debug(
                f"No status available for chunk {chunk.request_id}; scheduling next check."
            )
            self._schedule_next_chunk_check(chunk)
            return False

        if status.status == StatusEnum.FAILED:
            logger.error(
                f"Chunk {chunk.request_id} failed on API. Error: {status.error}"
            )
            chunk.mark_failed(status.error or "Unknown API error")
            return True

        if status.status == StatusEnum.COMPLETE:
            logger.debug(f"Chunk {chunk.request_id} complete, saving result.")
            try:
                self._save_chunk_result(chunk, status, req)
                chunk.mark_complete()
            except Exception as save_e:
                logger.error(
                    f"Failed to save result for completed chunk {chunk.request_id}: {save_e}",
                    exc_info=True,
                )
                chunk.mark_failed(f"Failed to save result: {str(save_e)}")
                return True
            return False

        logger.debug(
            f"Chunk {chunk.request_id} not yet complete (status={status.status}); scheduling next check."
        )
        self._schedule_next_chunk_check(chunk)
        return False

    def _save_chunk_result(
        self, chunk: ChunkInfo, status: MarkerStatus, req: ConversionRequest
    ) -> None:
        content = None
        if status.markdown is not None:
            content = status.markdown
        elif status.json_data is not None:
            content = json.dumps(status.json_data, indent=2)

        if content is None:
            logger.error(
                f"No content found in status payload for chunk {chunk.path.name}. API Status: {status.status}, Success: {status.success}, Error: {status.error}"
            )
            raise ResultProcessingError(
                f"No content (markdown/json) in completed API result for {chunk.path.name}"
            )

        if req.tmp_dir is None:
            raise ResultProcessingError(
                f"Request temporary directory is not set for request {req.request_id}."
            )
        if status.images and req.images_dir is None:
            raise ResultProcessingError(
                f"Request final images directory is not set for request {req.request_id}, but images were received."
            )

        temp_file = chunk.get_result_path(req.tmp_dir)
        logger.debug(f"Preparing to save chunk {chunk.index} result to {temp_file}")

        image_map = {}
        if status.images:
            image_map = self._process_chunk_images(
                status.images, chunk, req.tmp_dir, req.chunk_size, req.images_dir
            )
            if image_map:
                logger.debug(
                    f"Replacing {len(image_map)} image references in content for chunk {chunk.index}"
                )
                for original_name, new_ref in image_map.items():
                    content = content.replace(f"]({original_name})", f"]({new_ref})")

        logger.debug(
            f"Saving chunk {chunk.index} result ({len(content)} chars) to {temp_file}"
        )
        self.saver.save_content(content, temp_file)

    def _combine_and_save_result(self, req: ConversionRequest) -> None:
        try:
            if not req.target_file or not req.tmp_dir:
                raise ResultProcessingError(
                    f"Cannot combine results for {req.request_id}: Missing target_file or tmp_dir."
                )

            ensure_directory(req.target_file.parent)
            output_file, total_size = self.saver.combine_results(req)
            logger.debug(
                f"Successfully combined results for {req.request_id} to {output_file} ({total_size} bytes)"
            )
            logger.info(f"Successfully saved output to {output_file}")

            req.set_status(Status.COMPLETE)
            self.cache.save(req)

        except Exception as e:
            error_msg = (
                f"Failed to combine results for request {req.request_id}: {str(e)}"
            )
            logger.error(error_msg, exc_info=True)
            req.set_status(Status.FAILED, error_msg)
            self.cache.save(req)
            raise  # Propagate error to _handle_single_request

    def _move_final_images(self, req: ConversionRequest) -> None:
        if req.tmp_dir and req.target_file and req.images_dir:
            source_images_dir = req.tmp_dir / "images"
            if source_images_dir.exists():
                logger.debug(f"Moving final images for request {req.request_id}...")
                try:
                    self.saver.move_images(source_images_dir, req.images_dir)
                    logger.debug(
                        f"Successfully moved images for request {req.request_id}. Source temp dir will be cleaned up."
                    )
                except ResultProcessingError as img_err:
                    logger.error(
                        f"Failed to move final images for {req.request_id}: {img_err}"
                    )
            else:
                logger.debug(
                    f"No temporary images directory found at {source_images_dir} for request {req.request_id}. Nothing to move."
                )
        else:
            logger.debug(
                f"Skipping image move for request {req.request_id}: "
                "missing temp dir, target file path, or images directory."
            )

    def _cleanup_request(self, req: ConversionRequest) -> None:
        req_id = req.request_id
        logger.debug(
            f"Cleaning up resources for request {req_id} (Original: {req.original_file.name})..."
        )
        try:
            if req.tmp_dir and Path(req.tmp_dir).exists():
                logger.debug(f"Deleting temporary directory: {req.tmp_dir}")
                safe_delete(req.tmp_dir)
            else:
                logger.debug(
                    f"No temporary directory found or specified for request {req_id}. Nothing to delete."
                )

            logger.debug(f"Deleting cache entry for request {req_id}")
            deleted = self.cache.delete(req_id)
            if not deleted:
                logger.debug(
                    f"Cache entry for request {req_id} not found for deletion (may have been cleaned previously)."
                )

            logger.debug(f"Cleanup finished for request {req_id}.")
        except Exception as e:
            logger.error(
                f"Error during cleanup for request {req_id}: {e}", exc_info=False
            )