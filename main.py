import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from batch_processor import BatchProcessor
from common import ensure_directory, get_env_var
from result_handler import ResultHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

@dataclass
class ProcessingConfig:
    """Configuration for PDF processing."""
    input_path: str
    output_format: str = "markdown"
    langs: str = "English"
    use_llm: bool = False
    strip_existing_ocr: bool = False
    disable_image_extraction: bool = False
    force_ocr: bool = False
    paginate: bool = False
    chunk_size: int = 25

class MarkerProcessor:
    """Handles the core business logic for processing PDFs."""

    def __init__(self, api_key: str, cache_dir: Path = Path(".marker_cache"), output_dir: Path = Path("converted")):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        ensure_directory(self.cache_dir)
        ensure_directory(self.output_dir)

    def process(self, config: ProcessingConfig) -> None:
        """Process files according to configuration."""
        # Initialize processors
        batch_processor = BatchProcessor(self.api_key, self.cache_dir, chunk_size=config.chunk_size)
        result_handler = ResultHandler(self.api_key, self.cache_dir)

        try:
            # Process input path
            input_path = Path(config.input_path)
            if input_path.is_file():
                files_to_process = [input_path]
            else:
                files_to_process = list(input_path.glob("**/*"))

            # Process each file
            for file_path in files_to_process:
                if file_path.is_file():
                    logging.info(f"Processing {file_path}")
                    batch_processor.process_file(
                        file_path=file_path,
                        output_dir=self.output_dir,
                        output_format=config.output_format,
                        langs=config.langs,
                        use_llm=config.use_llm,
                        strip_existing_ocr=config.strip_existing_ocr,
                        disable_image_extraction=config.disable_image_extraction,
                        force_ocr=config.force_ocr,
                        paginate=config.paginate
                    )

            # Process results
            result_handler.process_cache_items()

            logging.info("All processing completed successfully.")
        finally:
            # Clean up resources
            batch_processor.close()
            result_handler.close()

class MarkerCLI:
    """Handles command line interface."""

    @staticmethod
    def parse_args() -> ProcessingConfig:
        """Parse command line arguments into ProcessingConfig."""
        parser = argparse.ArgumentParser(description="Process PDF files using Marker API.")
        parser.add_argument("input", help="Input file or directory path")
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        parser.add_argument("--langs", default="English", help="Comma-separated OCR languages")
        parser.add_argument("--llm", action="store_true", help="Use LLM for enhanced processing")
        parser.add_argument("--strip", action="store_true", help="Redo OCR processing")
        parser.add_argument("--noimg", action="store_true", help="Disable image extraction")
        parser.add_argument("--force", action="store_true", help="Force OCR on all pages")
        parser.add_argument("--pages", action="store_true", help="Add page delimiters")
        parser.add_argument("--max", action="store_true", help="Enable all OCR enhancements (LLM, strip OCR, force OCR)")
        parser.add_argument("--no-chunk", action="store_true", help="Disable PDF chunking (sets chunk size to 1 million)")
        parser.add_argument("-cs", "--chunk-size", type=int, help="Set PDF chunk size in pages", default=25)

        args = parser.parse_args()

        # If --no-chunk is specified, override chunk size to effectively disable chunking
        chunk_size = 1_000_000 if args.no_chunk else args.chunk_size

        return ProcessingConfig(
            input_path=args.input,
            output_format="json" if args.json else "markdown",
            langs=args.langs,
            use_llm=args.llm or args.max,
            strip_existing_ocr=args.strip or args.max,
            disable_image_extraction=args.noimg,
            force_ocr=args.force or args.max,
            paginate=args.pages,
            chunk_size=chunk_size
        )

def main():
    """Entry point for the CLI."""
    try:
        # Parse args and get API key
        config = MarkerCLI.parse_args()
        api_key = get_env_var("MARKER_PDF_KEY")

        # Create processor and run
        processor = MarkerProcessor(api_key)
        processor.process(config)

    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
