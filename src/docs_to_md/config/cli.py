import argparse
from pathlib import Path    
import os
from typing import Optional
import importlib.metadata

from docs_to_md.config.settings import Config
from docs_to_md.utils.exceptions import ConfigurationError, FileError


def parse_args() -> argparse.Namespace:
    # Get package version dynamically
    try:
        __version__ = importlib.metadata.version('pdf-to-markdown-cli')
    except importlib.metadata.PackageNotFoundError:
        __version__ = 'unknown' # Fallback if package not installed
        
    parser = argparse.ArgumentParser(
        description="Process PDF files using Marker API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Add version argument
    parser.add_argument(
        '--version',
        action='version',
        version=f'pdf-to-markdown-cli version: {__version__}'
    )
    
    parser.add_argument("input", help="Input file or directory path")
    
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    parser.add_argument("-l", "--langs", default="English", help="Comma-separated OCR languages")
    parser.add_argument("--llm", action="store_true", help="Use LLM for enhanced processing")
    parser.add_argument("--strip", action="store_true", help="Redo OCR processing")
    parser.add_argument("--noimg", action="store_true", help="Disable image extraction")
    parser.add_argument("--force", action="store_true", help="Force OCR on all pages")
    parser.add_argument("--pages", action="store_true", help="Add page delimiters")
    parser.add_argument("-mp", "--max-pages", type=int, help="Maximum number of pages to process from the start of the file")
    
    parser.add_argument("--max", action="store_true", help="Enable all OCR enhancements (LLM, strip OCR, force OCR)")
    parser.add_argument("--no-chunk", action="store_true", help="Disable PDF chunking (sets chunk size to 1 million)")
    parser.add_argument("-cs", "--chunk-size", type=int, help="Set PDF chunk size in pages", default=25)
    parser.add_argument("-o", "--output-dir", help="Absolute path to the output directory (default: same directory as input file)", default=None)

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose (DEBUG level) logging")
    
    return parser.parse_args()


def create_config_from_args() -> Config:
    args = parse_args()
    
    try:
        api_key = get_env_var("MARKER_PDF_KEY")
    except Exception as e:
        raise ConfigurationError(f"API key not found: {e}. Set the MARKER_PDF_KEY environment variable.")
        
    # If --no-chunk is specified, override chunk size to effectively disable chunking
    chunk_size = 1_000_000 if args.no_chunk else args.chunk_size
    
    config = Config(
        api_key=api_key,
        input_path=args.input,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        output_format="json" if args.json else "markdown",
        langs=args.langs,
        use_llm=args.llm or args.max,
        strip_existing_ocr=args.strip or args.max,
        disable_image_extraction=args.noimg,
        force_ocr=args.force or args.max,
        paginate=args.pages,
        chunk_size=chunk_size,
        max_pages=args.max_pages
    )
    
    config.validate()
    
    return config 

def get_env_var(name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement."""
    value = os.getenv(name)
    if required and not value:
        raise FileError(f"Required environment variable {name} is not set")
    return value