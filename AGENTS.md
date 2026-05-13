# PDF to Markdown CLI agent guide

This file is the compact implementation map for agents working in this repository. Keep it accurate when behavior, commands, package structure, or supported formats change.

## Project summary

`pdf-to-markdown-cli` is a Python 3.10+ CLI package that wraps the Datalab Marker API.

Primary command:

```bash
pdf-to-md <input-file-or-directory> [options]
```

Equivalent module entrypoint:

```bash
python -m docs_to_md <input-file-or-directory> [options]
```

The CLI converts supported files to Markdown by default, or to JSON/HTML when requested. It handles discovery, PDF chunking, API submission, polling, output assembly, image extraction, and cleanup.

## Source of truth

- Package metadata and dependencies: `pyproject.toml`.
- CLI arguments: `src/docs_to_md/config/cli.py`.
- Runtime config validation: `src/docs_to_md/config/settings.py`.
- Supported extensions and MIME types: `src/docs_to_md/api/models.py`.
- Marker API behavior reference: `datalab_marker_api_docs.md` (do not edit casually; it is copied API documentation).
- User-facing docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.

## Supported formats

Input extensions:

- PDF: `.pdf`
- Word: `.doc`, `.docx`, `.odt`
- PowerPoint: `.ppt`, `.pptx`, `.odp`
- Spreadsheets: `.xls`, `.xlsx`, `.ods`
- Web and ebook: `.html`, `.epub`
- Images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

Output formats:

- `markdown` -> `.md`
- `json` -> `.json`
- `html` -> `.html`

## Runtime requirements

- Python >= 3.10.
- `MARKER_PDF_KEY` must be set before running the CLI.
- Main dependencies: `backoff`, `diskcache`, `filetype`, `pikepdf`, `pydantic`, `ratelimit`, `requests`, `tqdm`.
- Datalab Marker endpoint: `https://www.datalab.to/api/v1/marker`.
- Client-side API limits in code: 150 requests/minute, 30 second request timeout, 3 retry attempts.

## Package map

- `src/docs_to_md/__main__.py`: module entrypoint that exits with `main()`.
- `src/docs_to_md/main.py`: console entrypoint, early verbose parsing, logging setup, top-level error handling.
- `src/docs_to_md/config/cli.py`: `argparse` parser, `--version`, `MARKER_PDF_KEY` lookup, `Config` creation.
- `src/docs_to_md/config/settings.py`: `Config` dataclass, input/output validation, cache/tmp directory setup with temp-dir fallback.
- `src/docs_to_md/api/client.py`: Marker submit/status calls, MIME detection, rate limiting, retries, request timeout.
- `src/docs_to_md/api/models.py`: API response models, API params, supported input/output mappings.
- `src/docs_to_md/core/paths.py`: output file and image directory naming with short UUID keys.
- `src/docs_to_md/core/processor.py`: file discovery, job preparation, PDF chunk submission, result workflow orchestration.
- `src/docs_to_md/core/result_handler.py`: polling loop, per-chunk backoff, chunk result saving, image reference rewriting, final assembly, cleanup.
- `src/docs_to_md/storage/cache.py`: diskcache wrapper for conversion request state.
- `src/docs_to_md/storage/models.py`: `ConversionRequest`, `ChunkInfo`, and status state transitions.
- `src/docs_to_md/utils/file_utils.py`: file discovery, safe deletion, directory creation, file IO helpers.
- `src/docs_to_md/utils/pdf_splitter.py`: PDF chunk creation with `pikepdf`.
- `src/docs_to_md/utils/logging.py`: root logging setup and `tqdm` progress wrapper.
- `src/docs_to_md/utils/exceptions.py`: project exception hierarchy.

## Execution flow

1. `main()` does a minimal parse for `-v`/`--verbose`, then configures logging.
2. `create_config_from_args()` parses all arguments, reads `MARKER_PDF_KEY`, builds `Config`, and validates it.
3. `MarkerProcessor` initializes `MarkerClient` and `CacheManager`.
4. `FileDiscovery.find_processable_files()` accepts a single file or recursively scans a directory.
5. `determine_output_paths()` creates the base output directory and assigns a short unique key.
6. `BatchProcessor` chunks PDFs when needed and submits every chunk or file to Marker.
7. `ResultHandler` polls chunk request IDs until completion or failure.
8. Completed chunk results are written to temporary files, images are decoded and references are rewritten.
9. Chunk outputs are combined into the final target file.
10. Temporary directories and cache entries are cleaned up for terminal requests.

## Output behavior

- Default output directory: same directory as the input file.
- Custom output directory: `-o`/`--output-dir`, and it must be absolute.
- Output file pattern: `<input_stem>_<unique_key>.<extension>`.
- Image directory pattern: `images_<unique_key>/`.
- Image directories are created only if Marker returns images.
- Markdown image references are rewritten to point at `images_<unique_key>/<image_name>`.

## CLI options

- `input`: required file or directory.
- `--json`: request JSON output.
- `--html`: request HTML output.
- `-l`, `--langs`: comma-separated OCR languages, default `English`.
- `--llm`: use Marker LLM enhancement.
- `--strip`: strip existing OCR and redo OCR.
- `--noimg`: disable image extraction.
- `--force`: force OCR on every page.
- `--pages`: add page delimiters.
- `-mp`, `--max-pages`: process only the first `N` pages.
- `--max`: equivalent to `--llm --strip --force`.
- `--no-chunk`: uses a very large chunk size to avoid practical chunking.
- `-cs`, `--chunk-size`: PDF pages per chunk, default `25`.
- `-o`, `--output-dir`: absolute output directory.
- `-v`, `--verbose`: debug logging.
- `--version`: installed package version.

## Testing

Run all tests:

```bash
python -m unittest discover -s tests -v
```

Current tests cover:

- CLI config parsing and HTML config selection in `tests/test_cli.py`.
- Output path generation in `tests/test_paths.py`.
- Config validation and writable cache fallback in `tests/test_settings.py`.
- File utility and image directory behavior in `tests/test_utils.py`.
- Mocked processing of bundled example PDFs in `tests/test_cli_equations.py`.

There are no live Datalab integration tests.

## Documentation rules for agents

- Keep docs aligned with code before making them more promotional.
- Do not claim resumable conversions unless a resume command or startup cache replay exists.
- Describe output names as UUID-keyed, not `_1`, `_2` collision suffixes.
- Treat `examples/*.md` as generated conversion outputs, not hand-authored docs.
- Leave `datalab_marker_api_docs.md` unchanged unless the task is specifically to refresh copied Datalab docs.
