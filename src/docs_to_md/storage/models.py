from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
import time


class Status(str, Enum):
    """Status of a request or chunk."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class ChunkInfo(BaseModel):
    """Information about a chunk or original file being processed."""

    path: Path
    index: int
    request_id: Optional[str] = None
    status: Status = Status.PENDING
    error: Optional[str] = None
    # Per-chunk polling state for exponential backoff in the result handler
    retry_attempts: int = 0
    retry_after: Optional[float] = None  # UNIX timestamp for next status check

    def mark_processing(self, request_id: str) -> None:
        self.request_id = request_id
        self.status = Status.PROCESSING
        self.retry_attempts = 0
        self.retry_after = None

    def mark_failed(self, error: str) -> None:
        self.status = Status.FAILED
        self.error = error
        self.retry_attempts = 0
        self.retry_after = None

    def mark_complete(self) -> None:
        self.status = Status.COMPLETE
        self.retry_attempts = 0
        self.retry_after = None

    def get_result_path(self, tmp_dir: Path) -> Path:
        return tmp_dir / f"{Path(self.path).name}.out"


class ConversionRequest(BaseModel):
    """Tracks a conversion request and its state."""

    request_id: str
    original_file: Path
    target_file: Path
    output_format: str = "markdown"
    status: Status = Status.PENDING
    error: Optional[str] = None
    chunks: List[ChunkInfo] = Field(default_factory=list)
    chunk_size: int
    tmp_dir: Optional[Path] = None
    images_dir: Optional[Path] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def _touch(self) -> None:
        self.updated_at = time.time()

    def set_status(self, status: Status, error: Optional[str] = None) -> None:
        self.status = status
        if error is not None:
            self.error = error
        elif status == Status.COMPLETE:
            self.error = None
        self._touch()

    def add_chunk(self, path: Path, index: int) -> ChunkInfo:
        chunk = ChunkInfo(path=path, index=index)
        self.chunks.append(chunk)
        self._touch()
        return chunk

    @property
    def pending_chunks(self) -> List[ChunkInfo]:
        return [
            c for c in self.chunks if c.status in (Status.PENDING, Status.PROCESSING)
        ]

    @property
    def ordered_chunks(self) -> List[ChunkInfo]:
        return sorted(self.chunks, key=lambda x: x.index)

    @property
    def has_failed(self) -> bool:
        return self.status == Status.FAILED or any(
            c.status == Status.FAILED for c in self.chunks
        )

    @property
    def all_complete(self) -> bool:
        return bool(self.chunks) and all(
            c.status == Status.COMPLETE for c in self.chunks
        )