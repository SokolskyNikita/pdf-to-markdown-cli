from enum import Enum
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
import time


class Status(str, Enum):
    """Status of a request or chunk."""
    PENDING = "pending"  # Waiting to be processed by the API
    PROCESSING = "processing"  # Currently being processed by the API
    COMPLETE = "complete"  # Successfully processed by the API
    FAILED = "failed"  # Failed to process by the API


class ChunkInfo(BaseModel):
    """Information about a chunk or original file being processed."""
    path: Path
    index: int
    request_id: Optional[str] = None
    status: Status = Status.PENDING
    error: Optional[str] = None

    def mark_processing(self, request_id: str) -> None:
        """Mark chunk as processing with given request ID."""
        self.request_id = request_id
        self.status = Status.PROCESSING

    def mark_failed(self, error: str) -> None:
        """Mark chunk as failed with error message."""
        self.status = Status.FAILED
        self.error = error

    def mark_complete(self) -> None:
        """Mark chunk as complete."""
        self.status = Status.COMPLETE

    def get_result_path(self, tmp_dir: Path) -> Path:
        """Get the path where the result should be stored."""
        return tmp_dir / f"{Path(self.path).name}.out"


class ConversionRequest(BaseModel):
    """Tracks a conversion request and its state."""
    request_id: str
    original_file: Path
    target_file: Path
    output_format: str = "markdown"
    status: Status = Status.PENDING
    error: Optional[str] = None
    # Use default_factory to avoid shared mutable list across instances
    chunks: List[ChunkInfo] = Field(default_factory=list)
    chunk_size: int
    tmp_dir: Optional[Path] = None  # Directory for temporary files for this conversion
    images_dir: Optional[Path] = None  # Added to store determined image path
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def set_status(self, status: Status, error: Optional[str] = None) -> None:
        """Set status and optional error message."""
        self.status = status
        if error:
            self.error = error

    def add_chunk(self, path: Path, index: int) -> ChunkInfo:
        """Add a new chunk and return it."""
        chunk = ChunkInfo(path=path, index=index)
        self.chunks.append(chunk)
        return chunk

    @property
    def pending_chunks(self) -> List[ChunkInfo]:
        """Get all pending or processing chunks."""
        return [c for c in self.chunks if c.status in (Status.PENDING, Status.PROCESSING)]

    @property
    def ordered_chunks(self) -> List[ChunkInfo]:
        """Get chunks ordered by index."""
        return sorted(self.chunks, key=lambda x: x.index)

    @property
    def has_failed(self) -> bool:
        """Check if any chunks have failed."""
        return any(c.status == Status.FAILED for c in self.chunks)

    @property
    def all_complete(self) -> bool:
        """Check if all chunks are complete."""
        return all(c.status == Status.COMPLETE for c in self.chunks) 