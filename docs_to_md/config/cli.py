import argparse
from pathlib import Path

from docs_to_md.config.settings import Config
from docs_to_md.utils.exceptions import ConfigurationError
from docs_to_md.utils.file_utils import get_env_var


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Process PDF files using Marker API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Required arguments
    parser.add_argument("input", help="Input file or directory path")
    
    # Output format
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    # OCR settings
    parser.add_argument("--langs", default="English", help="Comma-separated OCR languages")
    parser.add_argument("--llm", action="store_true", help="Use LLM for enhanced processing")
    parser.add_argument("--strip", action="store_true", help="Redo OCR processing")
    parser.add_argument("--noimg", action="store_true", help="Disable image extraction")
    parser.add_argument("--force", action="store_true", help="Force OCR on all pages")
    parser.add_argument("--pages", action="store_true", help="Add page delimiters")
    parser.add_argument("--max-pages", type=int, help="Maximum number of pages to process from the start of the file")
    
    # Advanced settings
    parser.add_argument("--max", action="store_true", help="Enable all OCR enhancements (LLM, strip OCR, force OCR)")
    parser.add_argument("--no-chunk", action="store_true", help="Disable PDF chunking (sets chunk size to 1 million)")
    parser.add_argument("-cs", "--chunk-size", type=int, help="Set PDF chunk size in pages", default=25)
    parser.add_argument("--output-dir", help="Output directory", default="converted")
    parser.add_argument("--cache-dir", help="Cache directory", default=".docs_to_md_cache")
    
    return parser.parse_args()


def create_config_from_args() -> Config:
    """
    Create configuration from command line arguments.
    
    Returns:
        Config object with settings from command line
        
    Raises:
        ConfigurationError: If required arguments are missing
    """
    args = parse_args()
    
    # Get API key from environment
    try:
        api_key = get_env_var("MARKER_PDF_KEY")
    except Exception as e:
        raise ConfigurationError(f"API key not found: {e}. Set the MARKER_PDF_KEY environment variable.")
        
    # If --no-chunk is specified, override chunk size to effectively disable chunking
    chunk_size = 1_000_000 if args.no_chunk else args.chunk_size
    
    config = Config(
        api_key=api_key,
        input_path=args.input,
        output_dir=Path(args.output_dir),
        cache_dir=Path(args.cache_dir),
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
    
    # Validate the configuration
    config.validate()
    
    return config 