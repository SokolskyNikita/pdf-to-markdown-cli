"""Run conversions: plan, split, convert chunks concurrently, assemble, write.

Everything here is backend-agnostic. How a chunk is actually converted is up to
the ``Backend`` (see ``backends/base.py``).
"""

from __future__ import annotations

import functools
import logging
import tempfile
import threading
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from docs_to_md.assemble import ChunkOutput, assemble, write_document
from docs_to_md.backends.base import Backend
from docs_to_md.config import Config
from docs_to_md.console import Console, format_cost
from docs_to_md.discovery import Job, display_path
from docs_to_md.errors import Cancelled, DocsToMdError, FatalAPIError, FileError
from docs_to_md.pdf import Chunk, count_pages, select_pages, split_pdf

logger = logging.getLogger(__name__)

CONVERTED, SKIPPED, FAILED = "converted", "skipped", "failed"


@dataclass
class FileResult:
    job: Job
    status: str
    message: str = ""
    pages: int = 0
    cost_cents: float = 0.0


@dataclass
class RunSummary:
    results: list[FileResult] = field(default_factory=list)
    elapsed: float = 0.0

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def pages(self) -> int:
        return sum(r.pages for r in self.results)

    @property
    def cost_cents(self) -> float:
        return sum(r.cost_cents for r in self.results)

    @property
    def exit_code(self) -> int:
        return 1 if self.count(FAILED) else 0


def _format_size(size: int) -> str:
    mib = size / (1024 * 1024)
    return f"{mib:g} MB" if mib >= 1 else f"{size} bytes"


class Pipeline:
    def __init__(
        self,
        config: Config,
        console: Console,
        backend: Backend | None = None,
        stop_event: threading.Event | None = None,
    ):
        self.config = config
        self.console = console
        self.stop_event = stop_event or threading.Event()
        self.backend = backend  # not needed for dry runs
        self._fatal_error: FatalAPIError | None = None

    # -- planning ---------------------------------------------------------

    def _existing_output(self, job: Job) -> Path | None:
        if self.config.overwrite:
            return None
        for path in (job.output, job.images_dir):
            if path.exists():
                return path
        return None

    def _dry_run(self, jobs: Sequence[Job], summary: RunSummary) -> RunSummary:
        for job in jobs:
            detail = ""
            if job.is_pdf:
                try:
                    pages = len(
                        select_pages(count_pages(job.source), self.config.page_range, self.config.max_pages)
                    )
                except DocsToMdError as e:
                    self.console.failure(f"{job.label}: {e}")
                    summary.results.append(FileResult(job, FAILED, str(e)))
                    continue
                size = self.config.chunk_size or pages or 1
                chunks = max(1, -(-pages // size))
                detail = f" ({pages} page{'s' * (pages != 1)}, {chunks} chunk{'s' * (chunks != 1)})"
            self.console.info(f"would convert {job.label} → {display_path(job.output)}{detail}")
            summary.results.append(FileResult(job, CONVERTED))
        return summary

    # -- per-chunk work (runs in worker threads) --------------------------

    def _check_cancelled(self, abort: threading.Event) -> None:
        if self.stop_event.is_set():
            raise Cancelled("Interrupted")
        if abort.is_set():
            raise Cancelled("Another chunk of this file failed")

    def _convert_chunk(self, chunk: Chunk, abort: threading.Event) -> ChunkOutput:
        assert self.backend is not None
        try:
            output = self.backend.convert(chunk, functools.partial(self._check_cancelled, abort))
        except Cancelled:
            raise
        except FatalAPIError as e:
            # Stop everything now rather than when the main thread reaches this file.
            self._fatal_error = self._fatal_error or e
            self.stop_event.set()
            raise
        except BaseException:
            abort.set()  # don't keep spending credits on this file's other chunks
            raise
        self.console.advance()
        return output

    # -- per-file orchestration (main thread) -----------------------------

    def _prepare(self, job: Job, work_dir: Path) -> list[Chunk]:
        if job.is_pdf:
            work_dir.mkdir(parents=True, exist_ok=True)
            return split_pdf(
                job.source,
                work_dir,
                self.config.chunk_size,
                self.config.page_range,
                self.config.max_pages,
            )
        assert self.backend is not None
        info = self.backend.info
        limit = info.max_upload_bytes
        if limit is not None and job.source.stat().st_size > limit:
            raise FileError(f"file is larger than {info.label}'s {_format_size(limit)} upload limit")
        return [Chunk(path=job.source)]

    def _finish(self, job: Job, futures: list[Future], abort: threading.Event) -> FileResult:
        try:
            outputs = [future.result() for future in futures]
            doc = assemble(
                outputs,
                self.config.output_format,
                job.images_dir.name,
                reflow_markdown=self.config.reflow_markdown,
            )
            write_document(doc, job.output, job.images_dir)
        except FatalAPIError:
            raise
        except Cancelled:
            if self.stop_event.is_set():
                raise
            return FileResult(job, FAILED, "cancelled")
        except Exception as e:  # one bad file must not stop the batch
            abort.set()
            for future in futures:
                future.cancel()
            if not isinstance(e, DocsToMdError):
                logger.debug("Unexpected error converting %s", job.source, exc_info=True)
            self.console.failure(f"{job.label}: {e}")
            return FileResult(job, FAILED, str(e))

        pages = sum(o.page_count for o in outputs)
        cost = sum(o.cost_cents for o in outputs)
        details = [f"{pages} page{'s' * (pages != 1)}"] if pages else []
        if cost:
            details.append(format_cost(cost))
        suffix = f" ({', '.join(details)})" if details else ""
        self.console.success(f"{job.label} → {display_path(job.output)}{suffix}")
        self.console.result_path(str(job.output))
        return FileResult(job, CONVERTED, pages=pages, cost_cents=cost)

    def run(self, jobs: Sequence[Job]) -> RunSummary:
        started = time.monotonic()
        summary = RunSummary()
        pending: list[Job] = []
        for job in jobs:
            existing = self._existing_output(job)
            if existing is not None:
                self.console.skipped(f"{job.label}: {display_path(existing)} exists (use --overwrite)")
                summary.results.append(FileResult(job, SKIPPED))
            else:
                pending.append(job)

        if self.config.dry_run:
            self._dry_run(pending, summary)
        elif pending:
            self._convert_all(pending, summary)
        summary.elapsed = time.monotonic() - started
        return summary

    def _convert_all(self, jobs: Sequence[Job], summary: RunSummary) -> None:
        if self.backend is None:
            raise FatalAPIError("No conversion backend configured")
        pool = ThreadPoolExecutor(max_workers=self.config.concurrency, thread_name_prefix="convert")
        try:
            with tempfile.TemporaryDirectory(prefix="pdf-to-md-") as tmp:
                scheduled = []
                total_chunks = 0
                for index, job in enumerate(jobs):
                    try:
                        chunks = self._prepare(job, Path(tmp) / str(index))
                    except DocsToMdError as e:
                        self.console.failure(f"{job.label}: {e}")
                        summary.results.append(FileResult(job, FAILED, str(e)))
                        continue
                    abort = threading.Event()
                    futures = [pool.submit(self._convert_chunk, c, abort) for c in chunks]
                    scheduled.append((job, futures, abort))
                    total_chunks += len(chunks)

                self.console.start_progress(total_chunks, "Converting")
                try:
                    for job, futures, abort in scheduled:
                        summary.results.append(self._finish(job, futures, abort))
                finally:
                    self.console.stop_progress()
        except BaseException as e:
            # Fatal API error or Ctrl-C: stop every worker promptly.
            self.stop_event.set()
            if isinstance(e, Cancelled) and self._fatal_error is not None:
                raise self._fatal_error from None
            raise
        finally:
            pool.shutdown(wait=not self.stop_event.is_set(), cancel_futures=True)
