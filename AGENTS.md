# pdf-to-md agent guide

This file is the compact implementation map for agents working in this repository. Keep it accurate when behavior, commands, module layout, or supported formats change.

## Project summary

`pdf-to-markdown-cli` is a Python 3.11+ CLI that converts documents to Markdown, HTML, or JSON with the Datalab Convert API (the default). It can also OCR documents to Markdown with Mistral OCR (`--backend mistral`), or transcribe PDFs and images with OpenAI's GPT-Luna, called directly (`--backend openai`) or through OpenRouter (`--backend openrouter`).

```bash
pdf-to-md INPUT [INPUT ...] [options]
python -m docs_to_md INPUT [INPUT ...] [options]
```

It discovers inputs, plans deterministic output paths, and splits PDFs into page chunks. It converts chunks concurrently through a conversion backend (`--backend`: `datalab`, `mistral`, `openai`, or `openrouter`), merges the chunk results (renumbering pages and renaming images), and writes the output atomically.

## Source of truth

- Package metadata, dependencies, and tool config (pytest, coverage, ruff): `pyproject.toml`.
- CLI options, exit codes, and help text: `src/docs_to_md/cli.py`.
- Output formats and extensions: `OUTPUT_EXTENSIONS` in `src/docs_to_md/assemble.py`.
- What each backend accepts (input extensions, output formats, modes, upload limit, API key variables): its `BackendInfo`, e.g. `DatalabBackend.info` in `src/docs_to_md/backends/datalab/backend.py`. Datalab MIME types: `src/docs_to_md/backends/datalab/models.py`.
- Datalab API reference: <https://documentation.datalab.to/api-reference/> (also `https://documentation.datalab.to/llms.txt`).
- OpenAI Responses API and file inputs: <https://developers.openai.com/api/docs/guides/file-inputs>. Append `.md` to any page URL for Markdown. Model prices: <https://developers.openai.com/api/docs/pricing.md>. OpenRouter's compatible API: <https://openrouter.ai/docs/api_reference/responses/overview.md>.
- Mistral OCR guide: <https://docs.mistral.ai/studio/document-processing/basic_ocr.md> (index at `https://docs.mistral.ai/llms.txt`), OpenAPI spec: <https://docs.mistral.ai/openapi.yaml>, prices: <https://mistral.ai/pricing>.
- User-facing docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.
- Model research (prices, benchmark scores, our sample-test results, and candidates for future remote and local backends): `docs/ocr-models.md`.
- Scanned-book benchmark (two-page scans, footnotes, printed spelling): `benchmarks/scanned_books/` (`README.md` there). Its scans are public domain; only add pages whose copyright has expired.

## Module map (`src/docs_to_md/`)

- `cli.py`: `build_parser()`, `config_from_args()` (including deprecated-flag mapping, backend API key lookup, and the backend's default `--chunk-size`), `main()` returning exit codes, `entrypoint()` (the console script; it hard-exits with `os._exit` on exit codes 2 and 130 so in-flight uploads don't delay exit).
- `config.py`: `Config` dataclass. `validate()` checks the output format, mode, `--model`, and API key against the selected backend's `BackendInfo`.
- `discovery.py`: `plan_jobs(..., input_extensions=...)` produces `Job(source, output, images_dir, label)`, considering only extensions the backend accepts. It skips hidden paths and generated image folders (new `<stem>_images/` and legacy `images_<key>/`). It also skips files recognizably generated for another input: `<name.ext><ext>` or `<stem>_converted<ext>` always, and a plain `<stem><ext>` only if its `<stem>_images/` exists. It resolves collisions case-insensitively and never plans an output onto an input.
- `pipeline.py`: backend-agnostic. `Pipeline.run()` skips existing outputs unless `--overwrite`, handles `--dry-run` (no backend needed; prints page counts and the backend class's `estimate_cents()`), splits PDFs, enforces the backend's upload limit for whole documents, runs `backend.convert()` for each chunk on a `ThreadPoolExecutor`, and returns a `RunSummary`. A failing chunk aborts its sibling chunks, unless `--keep-partial`, which lets them finish and writes a `<!-- pdf-to-md: page N failed: ... -->` placeholder per failed page (the file still counts as failed). A `FatalAPIError` in any worker stops the whole run.
- `backends/__init__.py`: the `BACKENDS` registry, `DEFAULT_BACKEND`, and `get_backend()`.
- `backends/base.py`: the contract. `BackendInfo` (capabilities used for validation and discovery, plus the default chunk size and model) and the `Backend` ABC: `from_config(config, stop_event)`, the optional classmethod `estimate_cents(config, pages)` for dry runs, and `convert(chunk, check_cancelled) -> ChunkOutput`, called concurrently from worker threads. Raise `FatalAPIError` for run-wide failures, let `Cancelled` from `check_cancelled` propagate, and raise any other `DocsToMdError` to fail just that file.
- `backends/datalab/backend.py`: `DatalabBackend` maps `Config` to Convert API fields (`options_for()`; page selection is sent only for documents uploaded whole), submits, polls with capped backoff until `--timeout`, and resubmits on page-rate-limit results.
- `backends/datalab/client.py`: `DatalabClient.submit()` / `get_result()`. It uses per-thread `requests.Session` objects and retries 408/429/5xx/529 and network errors, honoring `Retry-After`. 401/403/402 raise `FatalAPIError`. It fetches `result_url` when results aren't inline. Sleeps wake on the shared `stop_event`.
- `backends/datalab/models.py`: `ConvertOptions.to_form()`, `ConvertResult.from_payload()` (API fields `markdown`/`html`/`json`/`images`/`metadata`/`cost_breakdown`), `MODES`, and `INPUT_MIME_TYPES`.
- `backends/mistral/backend.py`: `MistralBackend` sends each chunk to `/v1/ocr` in one synchronous request: documents as `document_url`, images as `image_url`, both as base64 data URLs. Page selection (`pages`) is sent only for documents uploaded whole, and the API's page `index` numbers them. With `--split-spreads`, the halves from `spread_halves()` go in one request and `join_halves()` joins them. Pages are joined with `join_pages()`.
- `backends/mistral/client.py`: `MistralClient` subclasses `OpenAIClient` for its session and retry loop and classifies Mistral's error bodies (`{"detail": ...}` or `{"object": "error", "message", "type"}`). 401, 402, 403, and `invalid_model` raise `FatalAPIError`.
- `backends/mistral/models.py`: `OCRRequest.body()`, `parse_response()` (inlines `[tbl-N](tbl-N)` table placeholders, saves or drops `![img-N](img-N)` images), `requested_pages()`, `PRICES` per 1,000 pages, and `INPUT_MIME_TYPES`. Header and footer extraction is on except for OCR 3 (`KEEPS_HEADERS`), where it misplaces body text. OCR 4.x returns footnotes in `footer` (and, on two-page scans, sometimes in `header`), so `_notes()` appends them to the page minus page numbers and repeated running footers.
- `backends/openai/backend.py`: `OpenAIBackend` sends each chunk to the Responses API: PDFs as `input_file` at high detail, images as `input_image`. It asks for strict JSON with one string per page and joins pages with `join_pages()`. The default chunk size is 1 page. A 1-page request that comes back as several strings (the halves of a two-page scan) is joined. A larger chunk with the wrong count is retried once, then split and sent page by page. With `--split-spreads` (`BackendInfo.splits_spreads`), `spreads.spread_halves()` cuts each landscape page into halves, each half is sent on its own (`_transcribe_each()`), and `join_halves()` joins them back per source page. `--mode` maps to reasoning effort. `OpenRouterBackend` subclasses it with OpenRouter's URL and key, an `openai/` model prefix, and a `file-parser` plugin pinned to the `native` engine.
- `backends/openai/client.py`: `OpenAIClient.create_response()` (a `post()` to `/responses`) with the same retry rules as the Datalab client, plus retries of responses with status `failed` unless the error code marks a bad request (`PERMANENT_FAILURE_PREFIXES`). 401, 402, 403, `model_not_found`, and quota 429s raise `FatalAPIError`, except OpenRouter's content-policy 403, which fails only the file. A read timeout (`--timeout`) is not retried.
- `backends/openai/prompt.py`: `INSTRUCTIONS`, the transcription prompt, and `instructions_for()`. Measure prompt changes with the scanned-book benchmark.
- `backends/openai/models.py`: `TranscribeRequest.body()`, `parse_response()`, `cost_cents()`, and `estimate_cents()` (dry runs, from `ESTIMATED_TOKENS_PER_PAGE`). Cost comes from OpenRouter's `usage.cost`, or from `PRICES` with long-context and service-tier multipliers.
- `pdf.py`: `validate_page_range()`, `select_pages()`, `count_pages()`, `split_pdf()` → `Chunk(path, pages)`. Non-PDF documents become `Chunk(path)` with empty `pages`.
- `spreads.py`: two-page scans for `--split-spreads`. `split_spreads()` halves landscape pages wider than `SPREAD_ASPECT` and strips their invisible OCR text (OpenAI reads a cropped page's whole text layer); backends wrap it with `spread_halves()` and regroup their per-page text with `join_halves()`.
- `assemble.py`: `OUTPUT_EXTENSIONS` and `ChunkOutput`, whose `content` uses Marker's conventions with chunk-local page numbers. `assemble()` merges `ChunkOutput`s. It renumbers Markdown `{N}----` markers, `page-N-M` anchors and links, HTML `data-page-id`, and JSON `/page/N/` ids, content-refs, and `page` fields. It also makes image names unique and URL-encodes image links. `join_pages()` builds chunk content from per-page text for backends that return pages, and `failed_pages()` the `--keep-partial` stand-in for a failed chunk. `write_document()` writes atomically and replaces old images.
- `markdown.py`: `remove_duplicate_captions()` drops paragraphs that repeat an image's alt text. `normalize_superscripts()` rewrites LaTeX-only superscripts (`$^{a}$`) and Unicode superscript digits and modifier letters as `<sup>`, outside code fences, leaving `ª`/`º` alone (off with `--keep-superscripts`). `normalize_line_breaks()` joins hard-wrapped paragraphs and leaves structure alone.
- `console.py`: `Console` (status lines to stderr, result paths to stdout, tqdm progress, `NO_COLOR`), `setup_logging()`, `format_cost()` (tenths of a cent below $1, cents above), and `format_elapsed()`.
- `errors.py`: `DocsToMdError` → `ConfigurationError`, `FileError`, `PDFProcessingError`, `APIError` (→ `RetryableAPIError`, `FatalAPIError`), `ResultProcessingError`, `Cancelled`.

## Behavior contracts

- Output: `<stem><ext>` plus `<stem>_images/` (created only when there are images), next to the input or under `-o`, which mirrors directory structure. Same-stem inputs become `<name.ext><ext>`. Remaining clashes get `_2`, `_3` suffixes. An input whose output would be itself becomes `<stem>_converted<ext>`. Output files always use LF line endings.
- Existing outputs (the file or the images folder) are skipped unless `--overwrite`.
- stdout carries only converted output paths. Everything else goes to stderr.
- Exit codes: `0` ok, `1` one or more files failed, `2` usage/config/auth error, `130` interrupted.
- `datalab` is the default backend. Mistral and GPT-Luna run only when selected with `--backend`.
- API key lookup order: `--api-key`, then the backend's `api_key_env_vars` (Datalab: `DATALAB_API_KEY`, `MARKER_PDF_KEY`; Mistral: `MISTRAL_API_KEY`; OpenAI: `OPENAI_API_KEY`; OpenRouter: `OPENROUTER_API_KEY`). Backends with no env vars need no key.
- No state persists between runs. Temp files live in a `tempfile.TemporaryDirectory`.
- `--paginate` markers number source PDF pages from 0, the same as `--page-range`; a scan of two facing book pages is one page.
- Deprecated flags (`--llm`, `--max`, `--strip`, `--force`, `-l/--langs`, `--pages`, `--noimg`, `-cs`, `-mp`) stay accepted and hidden from `--help`.

## Supported formats

- Inputs depend on the backend. Datalab: `INPUT_MIME_TYPES` in `backends/datalab/models.py` (PDF, Word/ODT, PowerPoint/ODP, Excel/ODS/CSV, HTML, EPUB, PNG/JPEG/WEBP/GIF/TIFF). Mistral: `INPUT_MIME_TYPES` in `backends/mistral/models.py` (PDF, Word, PowerPoint, XLSX/CSV, ODT, and images including AVIF/HEIC/BMP), producing Markdown only. OpenAI and OpenRouter: `INPUT_MIME_TYPES` in `backends/openai/models.py` (PDF, PNG/JPEG/WEBP/GIF), producing Markdown or HTML only.
- Outputs: `markdown` → `.md`, `html` → `.html`, `json` → `.json` (each backend declares the subset it supports).

## Development

```bash
pip install -e ".[dev]"
pytest --cov                        # offline; no API calls
DATALAB_API_KEY=... pytest -m live -n 8  # real APIs in parallel, ~30 cents, a few minutes
# MISTRAL_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY add the Mistral and GPT-Luna live tests
ruff check . && ruff format --check .
python benchmarks/scanned_books/run.py --backend datalab --mode accurate  # real API, ~$0.12
```

- `tests/conftest.py` provides `FakeBackend` (synchronous in-memory backend for pipeline tests), `FakeClient` (stand-in for `DatalabClient`), a `CapturingConsole`, and an `examples` fixture that copies the alice and equations PDFs.
- `test_pipeline.py` tests orchestration with `FakeBackend`. `test_datalab_backend.py` tests Datalab request fields, polling, resubmits, and timeouts through the pipeline with `FakeClient`. `test_openai_backend.py` tests both GPT-Luna routes with `FakeResponses`: request bodies, page joining, page-count retries and the page-by-page fallback, and cost. `test_mistral_backend.py` tests Mistral with `FakeOCR`: request bodies, page selection, images, tables, footnotes from the header and footer, and cost.
- `tests/samples.py` is the manifest of every file in `examples/` (pages, language, required keywords). `test_samples.py` checks the PDFs and committed reference outputs offline. `test_live.py` (Datalab), `test_live_mistral.py` (Mistral OCR), and `test_live_llm.py` (GPT-Luna via OpenAI and OpenRouter) convert them for real. All use the marker `live` and are deselected by default.
- `benchmarks/scanned_books/`: 16 public-domain PDF pages (two-page spreads, footnotes, archaic spelling) with reference transcriptions (`reference/`), `manifest.py` (samples and spelling probes), `score.py` (word accuracy, footnotes, spelling probes, spread order), `run.py` (converts with this checkout and scores), `build_samples.py` (rebuilds the PDFs from the Internet Archive), and `baselines/` per backend and mode. `tests/test_benchmark.py` checks the fixtures and that the baselines keep their recorded scores; update its `EXPECTED` table when regenerating a baseline (`run.py --out benchmarks/scanned_books/baselines/<backend>-<mode>`) or correcting a reference.
- HTTP behavior is tested with `FakeSession`/`FakeResponse` from `conftest.py` in `tests/test_datalab_client.py`, `tests/test_mistral_client.py`, and `tests/test_openai_client.py`.
- To add a backend: subclass `Backend` under `backends/<name>/`, give it a `BackendInfo`, register it in `BACKENDS`, and emit `ChunkOutput` content in Marker's conventions so `assemble()` can merge it.
- CI (`ci.yml`) runs lint, tests on Linux (Python 3.11-3.14), macOS, and Windows, and a wheel smoke test. `live.yml` runs the live suite on manual dispatch using the `DATALAB_API_KEY` secret, plus the optional `MISTRAL_API_KEY`, `OPENAI_API_KEY`, and `OPENROUTER_API_KEY` secrets.

## Documentation rules for agents

- Keep docs aligned with code before making them more promotional.
- There is no resume across runs. Re-running skips finished outputs, which is the supported way to continue an interrupted batch.
- `examples/` pairs the test PDFs, public-domain excerpts from legitimate sources such as the Internet Archive, with outputs generated by the current version using the default Datalab backend. Regenerate them with `pdf-to-md examples --overwrite`; never hand-edit them.
- Releases: bump the version and changelog, push `main`, then push a `vX.Y.Z` tag. `.github/workflows/release.yml` builds the package, creates the GitHub release, and publishes to PyPI via Trusted Publishing.
- The README is also the PyPI page, so use absolute GitHub URLs for links to repository files.
