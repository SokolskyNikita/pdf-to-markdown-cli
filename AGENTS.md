# PDF to Markdown CLI - Agent Documentation

## Repository Purpose

CLI utility that wraps Datalab Marker API to convert PDFs and other supported documents (Word, PowerPoint, spreadsheets, EPUB, HTML, images) into Markdown/JSON/HTML via `docs_to_md` package. Published as "pdf-to-markdown-cli" on PyPI (current version 0.5.2).

## Supported Formats

**Input formats:**

- PDF
- Word (.doc/.docx)
- PowerPoint (.ppt/.pptx)
- Spreadsheets (.xls/.xlsx/.ods)
- EPUB, HTML
- Images (.png/.jpg/.jpeg/.webp/.gif/.tiff)

**Output formats:**

- Markdown (.md)
- JSON
- HTML

## Package Layout (26 Python files total)

- `src/docs_to_md/__main__.py`: module entry point via `sys.exit(main())`
- `src/docs_to_md/main.py`: console entrypoint with error handling, configuring logging and invoking MarkerProcessor
- `config/cli.py`: argparse-based CLI parsing with --version support, environment validation (MARKER_PDF_KEY); builds Config dataclass defined in config/settings.py. Supports --max flag for all enhancements
- `config/settings.py`: Config dataclass with validation, default paths `~/.docs_to_md/{cache,tmp}`, chunk_size=25 default
- `core/processor.py`: MarkerProcessor orchestrates job discovery, chunked submission via BatchProcessor, result polling, and cleanup. Uses ResultHandler for polling & assembly, and core/paths.py for deterministic output locations with collision avoidance
- `core/result_handler.py`: handles API polling, result combination, image extraction/rewriting, and final file output
- `api/client.py`: MarkerClient with rate limiting (150 req/min), exponential backoff, timeout handling, and filetype detection
- `api/models.py`: Pydantic schemas (MarkerStatus, SubmitResponse), supported format mappings, and API parameter definitions
- `storage/cache.py` & `storage/models.py`: CacheManager using diskcache for persistence of ConversionRequest/Status across runs
- `utils/file_utils.py`: FileDiscovery, TemporaryDirectory, FileIO, and get_unique_filename for collision handling
- `utils/pdf_splitter.py`: chunk_pdf_to_temp using pikepdf
- `utils/logging.py`: ProgressTracker with tqdm, setup_logging
- `utils/exceptions.py`: custom exception hierarchy

## Execution Flow

1. User invokes CLI (`pdf-to-md` script or `python -m docs_to_md`)
2. CLI parses args, reads MARKER_PDF_KEY, validates inputs, and instantiates MarkerProcessor
3. Processor discovers processable files, determines output/asset paths, and submits each file (chunked PDFs via chunk_pdf_to_temp)
4. Requests and chunk metadata persist via CacheManager
5. ResultHandler polls Marker API until chunks finish, saves markdown/JSON assets, rewrites image references, moves image outputs, and cleans temporary data

## Running & Configuration

**Requirements:**

- Python ≥3.10
- Dependencies from pyproject.toml: `backoff>=2.0`, `diskcache>=5.0`, `filetype>=1.0`, `pikepdf>=8.0`, `pydantic>=2.0`, `ratelimit>=2.0`, `requests>=2.0`, `tqdm>=4.0`
- Environment variable `MARKER_PDF_KEY` must be set for API auth (obtain from https://www.datalab.to/app/keys)

**Installation:**

- `pip install pdf-to-markdown-cli` OR `pip install -e .`
- Console script: `pdf-to-md` defined in pyproject.toml → `docs_to_md.main:main`

**Usage:**

- `pdf-to-md <input-path> [options]` or `python -m docs_to_md <input-path> [options]`

**Key CLI options:**

- `--json` (JSON output)
- `--langs "English,French"` (OCR languages)
- `--llm` (LLM enhancement)
- `--max` (all enhancements)
- `--chunk-size N`
- `--no-chunk`
- `-o /abs/output/path`
- `--verbose`
- `--version`

**API constraints:**

- 150 req/min rate limit
- 200MB file size limit
- 200 concurrent request limit
- 30s timeout
- 3 retry attempts

**Output behavior:**

- Outputs placed alongside input by default with unique suffix (\_1, \_2, etc.) for collision avoidance
- Image assets stored under `images_<unique_key>/` directory
- Results auto-deleted from Datalab servers after 1 hour

## Testing & Verification

- Test suite uses unittest in `tests/` directory (4 test files)
- Execute via `python -m unittest discover -s tests -v`
- Tests cover CLI config parsing (`test_cli.py`), output path determination (`test_paths.py`), config validation (`test_settings.py`), and utility helpers (`test_utils.py`)
- No integration tests with live API
- **NOTE:** Tests run via `python -m unittest discover -s tests -v` in a configured environment with package dependencies installed.

## File Structure & Examples

- `examples/` contains sample PDFs and their converted outputs: `alice_in_wonderland_sample.pdf` with both default and LLM versions, `equations.pdf` demonstrating math processing, associated `images/`
- `dist/` contains built packages from prior releases as both wheels (.whl) and source distributions (.tar.gz)
- `pyproject.toml` defines modern Python packaging with setuptools, entry points, dependencies, and metadata for PyPI publishing

## Additional Notes

- Cache/temp dirs default to `~/.docs_to_md/{cache,tmp}`; cleaned after successful runs via CacheManager and TemporaryDirectory context mgrs
- Project currently has many uncommitted changes (40+ modified files) including all source code, examples, and configuration files
- Supported file extensions: `.pdf`, `.xls/.xlsx/.ods`, `.doc/.docx/.odt`, `.ppt/.pptx/.odp`, `.html`, `.epub`, `.png/.jpg/.jpeg/.webp/.gif/.tiff`
- API endpoint: `https://www.datalab.to/api/v1/marker` with polling model
