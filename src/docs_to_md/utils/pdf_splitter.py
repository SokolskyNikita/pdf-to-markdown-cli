import logging
import uuid
from pathlib import Path
from typing import List, Optional

import pikepdf
from pydantic import BaseModel

from docs_to_md.utils.exceptions import PDFProcessingError
from docs_to_md.utils.file_utils import ensure_directory
from docs_to_md.utils.logging import ProgressTracker

logger = logging.getLogger(__name__)


class PDFChunkInfo(BaseModel):
    """Information about a single PDF chunk."""
    path: str
    index: int
    start_page: int
    end_page: int


class PDFChunks(BaseModel):
    """Collection of PDF chunks."""
    chunks: List[PDFChunkInfo]


def _create_chunk(pdf: pikepdf.Pdf, chunks_dir: Path, chunk_num: int, num_chunks: int, start: int, end: int) -> str:
    """
    Create a single PDF chunk.
    
    Args:
        pdf: Source PDF
        chunks_dir: Directory to save chunks
        chunk_num: Index of this chunk
        num_chunks: Total number of chunks
        start: Start page index (inclusive)
        end: End page index (exclusive)
        
    Returns:
        Path to created chunk file
        
    Raises:
        PDFProcessingError: If chunk creation fails
    """
    chunk_pdf = pikepdf.Pdf.new()
    try:
        for i in range(start, end):
            chunk_pdf.pages.append(pdf.pages[i])

        # Ensure safe path creation
        chunk_filename = f"{chunk_num+1:03d}of{num_chunks:03d}.pdf"
        chunk_path = str(chunks_dir / chunk_filename)
        
        chunk_pdf.save(
            chunk_path,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate
        )
        return chunk_path
    except Exception as e:
        raise PDFProcessingError(f"Failed to create PDF chunk {chunk_num+1}: {e}")
    finally:
        chunk_pdf.close()


def _create_chunks(pdf: pikepdf.Pdf, path: Path, pages_per_chunk: int, tmp_dir: Path) -> PDFChunks:
    """
    Create multiple chunks from a PDF.
    
    Args:
        pdf: Source PDF
        path: Original PDF path (for naming)
        pages_per_chunk: Number of pages per chunk
        tmp_dir: Directory to save chunks
        
    Returns:
        PDFChunks with information about created chunks
        
    Raises:
        PDFProcessingError: If chunking fails
    """
    # Use provided temp directory
    ensure_directory(tmp_dir)

    num_chunks = (len(pdf.pages) + pages_per_chunk - 1) // pages_per_chunk
    chunks: List[PDFChunkInfo] = []

    progress = ProgressTracker(num_chunks, "Chunking PDF", "chunk")
    
    try:
        for chunk_num in range(num_chunks):
            start = chunk_num * pages_per_chunk
            end = min(start + pages_per_chunk, len(pdf.pages))
            chunk_path = _create_chunk(pdf, tmp_dir, chunk_num, num_chunks, start, end)
            chunks.append(PDFChunkInfo(
                path=chunk_path,
                index=chunk_num,
                start_page=start,
                end_page=end-1
            ))
            progress.update()

        if not chunks:
            raise PDFProcessingError(f"Failed to create any chunks for {path}")

        return PDFChunks(chunks=chunks)
    
    finally:
        progress.close()


def chunk_pdf_to_temp(pdf_path: str, pages_per_chunk: int = 10, tmp_dir: Optional[Path] = None) -> Optional[PDFChunks]:
    """
    Split a PDF into chunks of specified size and save to temp directory.

    Args:
        pdf_path: Path to the PDF file
        pages_per_chunk: Number of pages per chunk (default: 10)
        tmp_dir: Directory to save chunks in (default: creates one)

    Returns:
        PDFChunks containing information about each chunk, or None if no chunking needed

    Raises:
        PDFProcessingError: If the PDF is invalid or cannot be processed
        ValueError: If pages_per_chunk < 1
    """
    if pages_per_chunk < 1:
        raise ValueError("pages_per_chunk must be at least 1")

    # Path validation needs to happen in the caller now or use a different util
    path = Path(pdf_path) 
    
    if not path.exists():
        raise PDFProcessingError(f"File does not exist: {pdf_path}")

    if path.suffix.lower() != '.pdf':
        raise PDFProcessingError(f"File is not a PDF: {pdf_path}")

    pdf = None
    try:
        pdf = pikepdf.Pdf.open(pdf_path)
        if len(pdf.pages) == 0:
            raise PDFProcessingError(f"PDF has no pages: {pdf_path}")

        if len(pdf.pages) <= pages_per_chunk:
            return None  # No chunking needed

        # Create temp directory if not provided
        if tmp_dir is None:
            # TODO: Consider making base temp dir configurable or use system temp
            tmp_dir = Path("chunks") / f"{path.stem}_{uuid.uuid4().hex[:8]}"
            ensure_directory(tmp_dir)

        return _create_chunks(pdf, path, pages_per_chunk, tmp_dir)

    except pikepdf.PdfError as e:
        raise PDFProcessingError(f"Invalid PDF {pdf_path}: {e}")
    except Exception as e:
        if isinstance(e, PDFProcessingError):
            raise
        raise PDFProcessingError(f"Error processing PDF {pdf_path}: {e}")
    finally:
        if pdf is not None:
            pdf.close() 