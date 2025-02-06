import uuid
from pathlib import Path
from typing import List, Optional

import pikepdf
from pydantic import BaseModel
from tqdm import tqdm

from common import ensure_directory


class PDFChunkInfo(BaseModel):
    """Information about a single PDF chunk."""
    path: str
    index: int
    start_page: int
    end_page: int

class PDFChunks(BaseModel):
    chunks: List[PDFChunkInfo]

class PDFError(Exception):
    """Base class for PDF processing errors."""
    pass

def _create_chunk(pdf: pikepdf.Pdf, chunks_dir: Path, chunk_num: int, num_chunks: int, start: int, end: int) -> str:
    """Create a single PDF chunk."""
    chunk_pdf = pikepdf.Pdf.new()
    try:
        for i in range(start, end):
            chunk_pdf.pages.append(pdf.pages[i])

        chunk_path = str(chunks_dir / f"{chunk_num+1:03d}of{num_chunks:03d}.pdf")
        chunk_pdf.save(
            chunk_path,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate
        )
        return chunk_path
    finally:
        chunk_pdf.close()

def _create_chunks(pdf: pikepdf.Pdf, path: Path, pages_per_chunk: int, tmp_dir: Path) -> PDFChunks:
    """Create chunks from PDF."""
    # Use provided temp directory
    ensure_directory(tmp_dir)

    num_chunks = (len(pdf.pages) + pages_per_chunk - 1) // pages_per_chunk
    chunks: List[PDFChunkInfo] = []

    with tqdm(total=num_chunks, desc="Chunking PDF", unit="chunk") as pbar:
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
            pbar.update(1)

    if not chunks:
        raise PDFError(f"Failed to create any chunks for {path}")

    return PDFChunks(chunks=chunks)

def chunk_pdf_to_temp(pdf_path: str, pages_per_chunk: int = 10, tmp_dir: Optional[Path] = None) -> Optional[PDFChunks]:
    """Split a PDF into chunks of specified size and save to temp directory.

    Args:
        pdf_path: Path to the PDF file
        pages_per_chunk: Number of pages per chunk (default: 10)
        tmp_dir: Directory to save chunks in (default: creates one)

    Returns:
        PDFChunks containing information about each chunk, or None if no chunking needed

    Raises:
        PDFError: If the PDF is invalid or cannot be processed
        ValueError: If pages_per_chunk < 1
    """
    if pages_per_chunk < 1:
        raise ValueError("pages_per_chunk must be at least 1")

    path = Path(pdf_path)
    if not path.exists():
        raise PDFError(f"File does not exist: {pdf_path}")

    if path.suffix.lower() != '.pdf':
        raise PDFError(f"File is not a PDF: {pdf_path}")

    try:
        with pikepdf.Pdf.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                raise PDFError(f"PDF has no pages: {pdf_path}")

            if len(pdf.pages) <= pages_per_chunk:
                return None  # No chunking needed

            # Create temp directory if not provided
            if tmp_dir is None:
                tmp_dir = Path("chunks") / f"{path.stem}_{uuid.uuid4().hex[:8]}"
                ensure_directory(tmp_dir)

            return _create_chunks(pdf, path, pages_per_chunk, tmp_dir)

    except pikepdf.PdfError as e:
        raise PDFError(f"Invalid PDF {pdf_path}: {e}")
    except Exception as e:
        if isinstance(e, PDFError):
            raise
        raise PDFError(f"Error processing PDF {pdf_path}: {e}")
