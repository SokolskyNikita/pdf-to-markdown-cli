# pdf-to-md agent guide

This file is the compact implementation map for agents working in this repository. Keep it accurate when behavior, commands, module layout, or supported formats change.

## Project summary

`pdf-to-markdown-cli` is a Python 3.10+ CLI that converts documents to Markdown, HTML, or JSON with the Datalab Convert API.

```bash
pdf-to-md INPUT [INPUT ...] [options]
python -m docs_to_md INPUT [INPUT ...] [options]
```

It discovers inputs, plans deterministic output paths, and splits PDFs into page chunks. It submits chunks concurrently, polls until each finishes, merges the chunk results (renumbering pages and renaming images), and writes the output atomically.

## Source of truth

- Package metadata, dependencies, and tool config (pytest, coverage, ruff): `pyproject.toml`.
- CLI options, exit codes, and help text: `src/docs_to_md/cli.py`.
- Supported input extensions, MIME types, and output formats: `src/docs_to_md/models.py`.
- Datalab API reference: <https://documentation.datalab.to/api-reference/> (also `https://documentation.datalab.to/llms.txt`).
- User-facing docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.

## Module map (`src/docs_to_md/`)

- `cli.py`: `build_parser()`, `config_from_args()` (including deprecated-flag mapping), `main()` returning exit codes, `entrypoint()` (the console script; it hard-exits with `os._exit` on exit codes 2 and 130 so in-flight uploads don't delay exit).
- `config.py`: `Config` dataclass with `validate()` and `convert_options()`. For PDFs, page selection is local and not sent to the API.
- `discovery.py`: `plan_jobs()` produces `Job(source, output, images_dir, label)`. It skips hidden paths and generated image folders (new `<stem>_images/` and legacy `images_<key>/`). It also skips files recognizably generated for another input: `<name.ext><ext>` or `<stem>_converted<ext>` always, and a plain `<stem><ext>` only if its `<stem>_images/` exists. It resolves collisions case-insensitively and never plans an output onto an input.
- `pipeline.py`: `Pipeline.run()` skips existing outputs unless `--overwrite`, handles `--dry-run`, splits PDFs, submits chunks to a `ThreadPoolExecutor`, polls with capped backoff until `--timeout`, resubmits on page-rate-limit results, and returns a `RunSummary`. A failing chunk aborts its sibling chunks. A `FatalAPIError` in any worker stops the whole run.
- `client.py`: `DatalabClient.submit()` / `get_result()`. It uses per-thread `requests.Session` objects and retries 408/429/5xx/529 and network errors, honoring `Retry-After`. 401/403/402 raise `FatalAPIError`. It fetches `result_url` when results aren't inline. Sleeps wake on the shared `stop_event`.
- `models.py`: `ConvertOptions.to_form()`, `ConvertResult.from_payload()` (API fields `markdown`/`html`/`json`/`images`/`metadata`/`cost_breakdown`), and the format tables.
- `pdf.py`: `validate_page_range()`, `select_pages()`, `count_pages()`, `split_pdf()` → `PdfChunk(path, pages)`.
- `assemble.py`: `assemble()` merges `ChunkOutput`s. It renumbers Markdown `{N}----` markers, `page-N-M` anchors and links, HTML `data-page-id`, and JSON `/page/N/` ids, content-refs, and `page` fields. It also makes image names unique and URL-encodes image links. `write_document()` writes atomically and replaces old images.
- `markdown.py`: `remove_duplicate_captions()` drops paragraphs that repeat an image's alt text. `normalize_line_breaks()` joins hard-wrapped paragraphs and leaves structure alone.
- `console.py`: `Console` (status lines to stderr, result paths to stdout, tqdm progress, `NO_COLOR`) and `setup_logging()`.
- `errors.py`: `DocsToMdError` → `ConfigurationError`, `FileError`, `PDFProcessingError`, `APIError` (→ `RetryableAPIError`, `FatalAPIError`), `ResultProcessingError`, `Cancelled`.

## Behavior contracts

- Output: `<stem><ext>` plus `<stem>_images/` (created only when there are images), next to the input or under `-o`, which mirrors directory structure. Same-stem inputs become `<name.ext><ext>`. Remaining clashes get `_2`, `_3` suffixes. An input whose output would be itself becomes `<stem>_converted<ext>`. Output files always use LF line endings.
- Existing outputs (the file or the images folder) are skipped unless `--overwrite`.
- stdout carries only converted output paths. Everything else goes to stderr.
- Exit codes: `0` ok, `1` one or more files failed, `2` usage/config/auth error, `130` interrupted.
- API key lookup order: `--api-key`, `DATALAB_API_KEY`, `MARKER_PDF_KEY`.
- No state persists between runs. Temp files live in a `tempfile.TemporaryDirectory`.
- Deprecated flags (`--llm`, `--max`, `--strip`, `--force`, `-l/--langs`, `--pages`, `--noimg`, `-cs`, `-mp`) stay accepted and hidden from `--help`.

## Supported formats

- Inputs: see `INPUT_MIME_TYPES` in `models.py` (PDF, Word/ODT, PowerPoint/ODP, Excel/ODS/CSV, HTML, EPUB, PNG/JPEG/WEBP/GIF/TIFF).
- Outputs: `markdown` → `.md`, `html` → `.html`, `json` → `.json`.

## Development

```bash
pip install -e ".[dev]"
pytest --cov                        # offline; no API calls
DATALAB_API_KEY=... pytest -m live  # real API, a few cents
ruff check . && ruff format --check .
```

- `tests/conftest.py` provides `FakeClient`, a `CapturingConsole`, and an `examples` fixture that copies the alice and equations PDFs.
- `tests/samples.py` is the manifest of every file in `examples/` (pages, language, required keywords). `test_samples.py` checks the PDFs and committed reference outputs offline. `test_live.py` (marker `live`, deselected by default) converts them for real.
- HTTP behavior is tested with a fake session in `tests/test_client.py`.
- CI (`ci.yml`) runs lint, tests on Linux (Python 3.10-3.14), macOS, and Windows, and a wheel smoke test. `live.yml` runs the live suite on manual dispatch using the `DATALAB_API_KEY` secret.

## Documentation rules for agents

- Keep docs aligned with code before making them more promotional.
- There is no resume across runs. Re-running skips finished outputs, which is the supported way to continue an interrupted batch.
- `examples/` pairs the test PDFs with outputs generated by the current version. Regenerate them with `pdf-to-md examples --overwrite`; never hand-edit them.
- Releases: bump the version and changelog, push `main`, then push a `vX.Y.Z` tag. `.github/workflows/release.yml` builds the package, creates the GitHub release, and publishes to PyPI via Trusted Publishing.
- The README is also the PyPI page, so use absolute GitHub URLs for links to repository files.
