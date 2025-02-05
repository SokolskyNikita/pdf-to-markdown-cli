import argparse
import time
from diskcache import Cache
from marker_lib import MarkerClient, MarkerRequestBuilder
import base64
import json
import re
from datetime import datetime
from pydantic import BaseModel
from pathlib import Path
import logging
import sys
from slugify import slugify
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

API_KEY = os.getenv("MARKER_PDF_KEY")
if not API_KEY:
    logging.error("MARKER_PDF_KEY environment variable is not set")
    sys.exit(1)

CACHE_DIR = ".marker_cache"
CHECK_INTERVAL = 15

def get_date_time():
    return datetime.now().strftime("%y-%m-%d_%H-%M")


class CacheEntry(BaseModel):
    extension: str
    original_filename: str


class CacheManager:
    def __init__(self, cache_dir):
        self.cache = Cache(cache_dir)

    def store_request(self, request_id, extension, filename):
        self.cache[request_id.strip()] = CacheEntry(
            extension=extension, original_filename=filename
        ).model_dump()
        logging.info(f"Cached request {request_id} for file '{filename}'")

    def get_request(self, request_id):
        if data := self.cache.get(request_id):
            return CacheEntry.model_validate(data)
        return None

    def remove_request(self, request_id):
        self.cache.pop(request_id)

    def get_pending_requests(self):
        return list(self.cache.iterkeys())


class ResultHandler:
    def _read_file(self, path):
        try:
            path_obj = Path(path)
            return path_obj.name, path_obj.read_bytes()
        except Exception as e:
            logging.error(f"Failed to read file {path}: {e}")
            return None, None

    def save_result(self, result, cache_data, output_dir=None):
        filename = cache_data.original_filename or "unknown.md"

        base_path = Path(output_dir or "converted")
        output_path = base_path / filename / get_date_time()
        output_path.mkdir(parents=True, exist_ok=True)

        if result.images:
            images_dir = output_path / ""
            images_dir.mkdir(exist_ok=True)
            for name, b64_data in result.images.items():
                (images_dir / name).write_bytes(base64.b64decode(b64_data))

        if content := (result.markdown or result.json_data):
            output_file = output_path / f"{filename}{cache_data.extension}"
            output_file.write_text(
                json.dumps(content) if isinstance(content, dict) else content
            )
            logging.info(f"Saved output to {output_file}")
            return output_file

        logging.error("No content found in conversion result")
        return None


class MarkerController:
    def __init__(self, api_key, cache_dir):
        self.client = MarkerClient(api_key)
        self.cache_manager = CacheManager(cache_dir)
        self.result_handler = ResultHandler()

    def _clean_filename(self, filename):
        # Split filename and extension
        path = Path(filename)
        original_extension = path.suffix
        name_without_ext = path.stem

        # Extract year: replace non-numeric characters with spaces, find the latest 4-digit number
        numbers = re.sub(r"[^\dA-Za-z]", " ", name_without_ext)
        years = [int(num) for num in re.findall(r"\b\d{4}\b", numbers)]
        year = max(years) if years else None

        # Extract title: stop at the first occurrence of " x" where x is not alphanumeric
        title_part = re.split(r"\s[^A-Za-z0-9]", name_without_ext, maxsplit=1)[0]
        title = slugify(
            title_part, separator=" ", lowercase=False, regex_pattern=r"[^A-Za-z\s]"
        )
        title = "_".join(word.capitalize() for word in title.split())

        if not title.strip():
            return filename

        # Return formatted filename with original extension
        return f"{title}-{year}{original_extension}" if year else f"{title}{original_extension}"

    def process_file(
        self,
        file_path,
        output_format="markdown",
        langs=None,
        use_llm=False,
        strip_existing_ocr=False,
        disable_image_extraction=False,
        force_ocr=False,
        paginate=False,
    ):
        path = Path(file_path)
        name = self._clean_filename(path.name)
        logging.info(f"Processing file: {name}")

        try:
            with open(path, "rb") as f:
                file_data = f.read()
            logging.info(f"Successfully read file: {len(file_data)} bytes")
        except Exception as e:
            logging.error(f"Failed to read file {path}: {e}")
            return

        try:
            builder = MarkerRequestBuilder(
                file_name=name,
                file_data=file_data,
                output_format=output_format,
                langs=langs if langs else "English",
                use_llm=use_llm,
                strip_existing_ocr=strip_existing_ocr,
                disable_image_extraction=disable_image_extraction,
                force_ocr=force_ocr,
                paginate=paginate,
            )
            logging.info("Created MarkerRequestBuilder")

            if result := self.client.send_request(builder):
                request_id, extension = result
                logging.info(f"Request submitted successfully. ID: {request_id}")
                self.cache_manager.store_request(request_id, extension, name)
            else:
                logging.error("send_request returned None")
        except Exception as e:
            logging.error(f"Error processing file: {e}")
            return

    def process_pending_requests(self, output_dir=None):
        request_ids = self.cache_manager.get_pending_requests()
        if not request_ids:
            return False

        still_pending = False
        for request_id in request_ids:
            status = self.client.process_status(request_id)

            if status.is_complete:
                if cache_data := self.cache_manager.get_request(request_id):
                    self.cache_manager.remove_request(request_id)
                    if status.result:
                        self.result_handler.save_result(
                            status.result, cache_data, output_dir
                        )
            else:
                still_pending = True
                logging.info(f"Request {request_id} still processing")

        return still_pending


def main():
    parser = argparse.ArgumentParser(description="Convert documents using Marker API")
    parser.add_argument("file", help="Input file path")
    parser.add_argument(
        "--outdir", help="Output directory (default: converted/<name>_<timestamp>/)"
    )
    parser.add_argument("--langs", help="OCR languages (comma-separated)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--llm", action="store_true", help="Use LLM to enhance accuracy"
    )
    parser.add_argument("--strip", action="store_true", help="Strip and redo OCR")
    parser.add_argument("--noimg", action="store_true", help="Disable image extraction")
    parser.add_argument("--force", action="store_true", help="Force OCR on all pages")
    parser.add_argument("--pages", action="store_true", help="Add page delimiters")
    parser.add_argument(
        "--max",
        action="store_true",
        help="Enable all OCR enhancements (LLM, strip OCR, force OCR)",
    )

    args = parser.parse_args()
    if not args.file:
        parser.print_help()
        return

    logging.info(f"Starting processing of file: {args.file}")
    try:
        controller = MarkerController(API_KEY, CACHE_DIR)
        logging.info("Initialized MarkerController")
        
        if not Path(args.file).exists():
            logging.error(f"Input file not found: {args.file}")
            sys.exit(1)
            
        controller.process_file(
            args.file,
            output_format="json" if args.json else "markdown",
            langs=args.langs,
            use_llm=args.llm or args.max,
            strip_existing_ocr=args.strip or args.max,
            disable_image_extraction=args.noimg,
            force_ocr=args.force or args.max,
            paginate=args.pages,
        )
        logging.info("File submitted for processing")

        while controller.process_pending_requests(args.outdir):
            logging.info("Waiting for processing to complete...")
            time.sleep(CHECK_INTERVAL)
        logging.info("Processing completed")

    except Exception as e:
        logging.error(f"Error processing file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
