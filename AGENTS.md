# pdf-to-md agent guide

This file is the compact implementation map for agents working in this repository. Keep it accurate when behavior, commands, module layout or supported formats change.

## Project summary

`pdf-to-markdown-cli` is a Python 3.11+ CLI that converts documents to Markdown, HTML or JSON with the Datalab Convert API (the default). It can also OCR documents to Markdown with Mistral OCR (`--backend mistral`) or transcribe PDFs and images with OpenAI's GPT-6 Luna (`gpt-6-luna`), called directly (`--backend openai`) or through OpenRouter (`--backend openrouter`).

```bash
pdf-to-md INPUT [INPUT ...] [options]
python -m docs_to_md INPUT [INPUT ...] [options]
```

It discovers inputs, plans deterministic output paths and splits PDFs into page chunks. It converts chunks concurrently through a conversion backend (`--backend`: `datalab`, `mistral`, `openai` or `openrouter`), merges the chunk results (renumbering pages and renaming images) and writes the output atomically.

## Source of truth

- Package metadata, version, dependencies and tool config (pytest, coverage, ruff): `pyproject.toml`. `src/docs_to_md/__init__.py` reads the installed package version; it has no separate version constant to bump.
- CLI options, exit codes and help text: `src/docs_to_md/cli.py`.
- Output formats and extensions: `OUTPUT_EXTENSIONS` in `src/docs_to_md/assemble.py`.
- What each backend accepts (input extensions, output formats, modes, upload limit, API key variables): its `BackendInfo`, e.g. `DatalabBackend.info` in `src/docs_to_md/backends/datalab/backend.py`. Datalab MIME types: `src/docs_to_md/backends/datalab/models.py`.
- Datalab API reference: <https://documentation.datalab.to/api-reference/> (also `https://documentation.datalab.to/llms.txt`).
- OpenAI Responses API and file inputs: <https://developers.openai.com/api/docs/guides/file-inputs>. Append `.md` to any page URL for Markdown. Model prices: <https://developers.openai.com/api/docs/pricing.md>. OpenRouter's compatible API: <https://openrouter.ai/docs/api_reference/responses/overview.md>.
- Mistral OCR guide: <https://docs.mistral.ai/studio/document-processing/basic_ocr.md> (index at `https://docs.mistral.ai/llms.txt`), OpenAPI spec: <https://docs.mistral.ai/openapi.yaml>, prices: <https://mistral.ai/pricing>.
- Usage and CLI reference: `README.md`. Runtime internals and implementation rationale: `HOW-IT-WORKS.md`. Development setup, conventions and release steps: `CONTRIBUTING.md`. Release history: `CHANGELOG.md`.
- Sample provenance and usage: `examples/README.md`. Sample expectations and reference-output modes: `tests/samples.py`.
- Model research (prices, benchmark scores, our sample-test results and candidates for future remote and local backends): `docs/ocr-models.md`.
- Scanned-book benchmark (two-page scans, footnotes, printed spelling): `benchmarks/scanned_books/` (`README.md` there). Its scans are public domain; only add pages whose copyright has expired.

## Module map (`src/docs_to_md/`)

- `cli.py`: `build_parser()`, `config_from_args()` (including deprecated-flag mapping, backend API key lookup and the backend's default `--chunk-size`), `main()` returning exit codes, `entrypoint()` (the console script; it hard-exits with `os._exit` on exit codes 2 and 130 so in-flight uploads don't delay exit).
- `config.py`: `Config` dataclass. `validate()` checks backend capabilities, API key, positive numeric limits, page-range syntax and the output directory. It rejects `--keep-partial` with JSON and `--split-spreads` for backends without `splits_spreads`. Backend-specific chunk defaults are applied by `config_from_args()`, not by constructing `Config` directly.
- `discovery.py`: `plan_jobs(..., input_extensions=...)` produces `Job(source, output, images_dir, label)`, considering only extensions the backend accepts. Directory traversal skips hidden files/directories and recognizable generated image folders (new `<stem>_images/` and legacy `images_<key>/`); explicitly named hidden inputs are accepted. It also skips files recognizably generated for another discovered input in the selected output format: `<name.ext><ext>` or `<stem>_converted<ext>` directly and a plain `<stem><ext>` only if its `<stem>_images/` exists. It resolves collisions case-insensitively and never plans an output onto an input.
- `pipeline.py`: backend-agnostic. `Pipeline.run()` skips existing outputs unless `--overwrite`, splits PDFs, runs `backend.convert()` for each chunk on a `ThreadPoolExecutor` and returns a `RunSummary`. It prechecks upload size only for non-PDF inputs; PDFs and their chunks are not size-checked locally. Dry runs need no backend instance: they count selected PDF pages/chunks locally and call the backend class's `estimate_cents()` for cost; non-PDF costs remain unestimated. These estimates do not account for spread splitting or retries. A failing chunk signals its siblings to abort, unless `--keep-partial` allows recoverable `DocsToMdError` failures to become per-page placeholders. `FatalAPIError` stops the whole run.
- `backends/__init__.py`: the `BACKENDS` registry, `DEFAULT_BACKEND` and `get_backend()`.
- `backends/base.py`: the contract. `BackendInfo` (capabilities used for validation and discovery, plus the default chunk size and model) and the `Backend` ABC: `from_config(config, stop_event)`, the optional classmethod `estimate_cents(config, pages)` for dry runs and `convert(chunk, check_cancelled) -> ChunkOutput`, called concurrently from worker threads. Raise `FatalAPIError` for run-wide failures, let `Cancelled` from `check_cancelled` propagate and raise any other `DocsToMdError` to fail just that file.
- `backends/datalab/backend.py`: `DatalabBackend` maps `Config` to Convert API fields (`options_for()`; page selection is sent only for documents uploaded whole), submits, polls with capped backoff until `--timeout` and resubmits on page-rate-limit results.
- `backends/datalab/client.py`: `DatalabClient.submit()` / `get_result()`. It uses per-thread `requests.Session` objects and retries 408/429/500/502/503/504/529 and transient network errors, honoring numeric `Retry-After`. Authenticated 401/403 and all 402 responses raise `FatalAPIError`; 401/403 from signed result-download links fail only the file. It fetches `result_url` when results aren't inline. Sleeps wake on the shared `stop_event`.
- `backends/datalab/models.py`: `ConvertOptions.to_form()`, `ConvertResult.from_payload()` (API fields `markdown`/`html`/`json`/`images`/`metadata`/`cost_breakdown`), `MODES` and `INPUT_MIME_TYPES`.
- `backends/mistral/backend.py`: `MistralBackend` sends each chunk to `/v1/ocr` in one synchronous request: documents as `document_url`, images as `image_url`, both as base64 data URLs. Page selection (`pages`) is sent only for documents uploaded whole and the API's page `index` numbers them. With `--split-spreads`, the halves from `spread_halves()` go in one request and `join_halves()` joins them. Pages are joined with `join_pages()`.
- `backends/mistral/client.py`: `MistralClient` subclasses `OpenAIClient` for its sessions, retry statuses and retry loop, including no retry on read timeout. It classifies Mistral's error bodies (`{"detail": ...}` or `{"object": "error", "message", "type"}`). 401, 402, 403 and `invalid_model` raise `FatalAPIError`.
- `backends/mistral/models.py`: `OCRRequest.body()`, `parse_response()` (inlines `[tbl-N](tbl-N)` table placeholders, saves or drops `![img-N](img-N)` images), `requested_pages()`, `PRICES` per 1,000 pages and `INPUT_MIME_TYPES`. Header and footer extraction is on except for OCR 3 (`KEEPS_HEADERS`), where it misplaces body text. OCR 4.1 returns footnotes in `footer` (and, on two-page scans, sometimes in `header`), so `_notes()` appends them to the page minus page numbers and repeated running footers.
- `backends/openai/backend.py`: `OpenAIBackend` sends each chunk to the Responses API: PDFs as `input_file` at high detail, images as `input_image`. It asks for strict JSON with one string per page and joins pages with `join_pages()`. The default chunk size is 1 page. A 1-page request that comes back as several strings (the halves of a two-page scan) is joined. A larger chunk with the wrong count is retried once, then split and sent page by page. With `--split-spreads`, `spread_halves()` splits eligible pages, `_transcribe_each()` sends each resulting page on its own and `join_halves()` regroups text per source page. `--mode` maps to reasoning effort. `OpenRouterBackend` subclasses it with OpenRouter's URL and key, an `openai/` model prefix and a `file-parser` plugin pinned to the `native` engine.
- `backends/openai/client.py`: `OpenAIClient.create_response()` posts to `/responses`. It retries 408/409/429/500/502/503/504, transient network errors and responses with status `failed` unless their code matches `PERMANENT_FAILURE_PREFIXES`. Fatal errors are 401/402/403, 404 with `model_not_found` and 429 with a code in `QUOTA_ERROR_CODES`. A 403 whose code ends with `content_policy_violation` fails only the file, regardless of provider. Read timeouts (`--timeout`) are not retried. Sessions, backoff and cancellation follow the same pattern as Datalab, but their retry-status sets differ.
- `backends/openai/prompt.py`: `INSTRUCTIONS`, the transcription prompt and `instructions_for()`. Measure prompt changes with the scanned-book benchmark.
- `backends/openai/models.py`: `TranscribeRequest.body()`, `parse_response()`, `cost_cents()` and `estimate_cents()` (dry runs, from `ESTIMATED_TOKENS_PER_PAGE`). Cost comes from OpenRouter's `usage.cost` or from `PRICES` with long-context and service-tier multipliers.
- `pdf.py`: `validate_page_range()`, `select_pages()`, `count_pages()`, `split_pdf()` → `Chunk(path, pages)`. Selection sorts and deduplicates page indexes, ignores indexes past the end, then applies `max_pages` to the selected list. Selection remains local even with `--no-chunk`. A complete PDF that fits in one chunk is reused as-is. The pipeline wraps non-PDF inputs in `Chunk(path)` with empty `pages`, leaving selection to the backend API.
- `spreads.py`: two-page scans for `--split-spreads`. `split_spreads()` halves unrotated pages whose width/height exceeds `SPREAD_ASPECT` (1.2). Rotated and narrower pages stay whole. Split copies lose invisible OCR text because OpenAI reads a cropped page's whole text layer; visible text and the source file are preserved. Backends use `spread_halves()` and regroup per-page text with `join_halves()`.
- `assemble.py`: `OUTPUT_EXTENSIONS` and `ChunkOutput`, whose `content` uses Marker's conventions with chunk-local page numbers. `assemble()` merges chunks in the supplied order. It renumbers Markdown `{N}` plus 48 dashes, `page-N-M` anchors and links, HTML `data-page-id` and JSON `/page/N/` ids, content-refs, `page` and `page_id` fields. It also makes image names unique and URL-encodes image links. `join_pages()` builds chunk content from per-page text; `failed_pages()` builds Markdown/HTML failure comments. `write_document()` stages the document and images, then atomically replaces the document file. The document and images directory are not replaced as a single transaction.
- `markdown.py`: `remove_duplicate_captions()` drops paragraphs that repeat an image's alt text. `normalize_superscripts()` rewrites LaTeX-only superscripts (`$^{a}$`) and Unicode superscript digits and modifier letters as `<sup>`, outside code fences, leaving `ª`/`º` alone (off with `--keep-superscripts`). `normalize_line_breaks()` joins hard-wrapped paragraphs and leaves structure alone.
- `console.py`: `Console` (status lines to stderr, result paths to stdout, tqdm progress, `NO_COLOR`), `setup_logging()`, `format_cost()` (tenths of a cent below $1, cents above) and `format_elapsed()`.
- `errors.py`: `DocsToMdError` → `ConfigurationError`, `FileError`, `PDFProcessingError`, `APIError` (→ `RetryableAPIError`, `FatalAPIError`), `ResultProcessingError`, `Cancelled`.

## Behavior contracts

- Output: `<stem><ext>` plus `<stem>_images/` (created only when there are images), next to the input or under `-o`, which mirrors directory structure. Same-stem inputs become `<name.ext><ext>`. Remaining clashes get `_2`, `_3` suffixes. An input whose output would be itself becomes `<stem>_converted<ext>`. Output files always use LF line endings.
- Existing outputs (the file or the images folder) are skipped unless `--overwrite`.
- During conversion, stdout carries only successfully converted output paths. Status, logs, errors and dry-run previews go to stderr. `--help` and `--version` use stdout.
- Exit codes: `0` ok, `1` one or more files failed or no supported inputs were found, `2` usage/config/fatal API error, `130` interrupted.
- `datalab` is the default backend. Mistral and GPT-Luna run only when selected with `--backend`.
- API key lookup order: `--api-key`, then the backend's `api_key_env_vars` (Datalab: `DATALAB_API_KEY`, `MARKER_PDF_KEY`; Mistral: `MISTRAL_API_KEY`; OpenAI: `OPENAI_API_KEY`; OpenRouter: `OPENROUTER_API_KEY`). Backends with no env vars need no key.
- No run state persists between invocations. Temporary chunks live in `tempfile.TemporaryDirectory`; interrupted documents restart from the beginning. This is separate from Datalab's server-side result cache (`--skip-cache`).
- `--keep-partial` works only with Markdown or HTML. Recoverable chunk failures produce `<!-- pdf-to-md: page N failed: ... -->` placeholders; the file still counts as failed, exits with status 1 and is omitted from stdout. If all chunks fail, nothing is written. Fatal API errors and cancellation do not produce partial output. Existing partial outputs require `--overwrite` to retry.
- `--paginate` markers number source PDF pages from 0, the same as `--page-range`; a scan of two facing book pages is one page.
- Deprecated flags (`--llm`, `--max`, `--strip`, `--force`, `-l/--langs`, `--pages`, `--noimg`, `-cs`, `-mp`) stay accepted and hidden from `--help`.

## Supported formats

- Inputs depend on the backend. Datalab: `INPUT_MIME_TYPES` in `backends/datalab/models.py` (PDF, Word/ODT, PowerPoint/ODP, Excel/ODS/CSV, HTML, EPUB, PNG/JPEG/WEBP/GIF/TIFF). Mistral: `INPUT_MIME_TYPES` in `backends/mistral/models.py` (PDF, Word, PowerPoint, XLSX/CSV, ODT and images including AVIF/HEIC/BMP), producing Markdown only. OpenAI and OpenRouter: `INPUT_MIME_TYPES` in `backends/openai/models.py` (PDF, PNG/JPEG/WEBP/GIF), producing Markdown or HTML only.
- Outputs: `markdown` → `.md`, `html` → `.html`, `json` → `.json` (each backend declares the subset it supports).

## Development

```bash
pip install -e ".[dev]"
pytest --cov                        # offline; no API calls
DATALAB_API_KEY=... pytest -m live -n 8  # real APIs; each enabled service bills its calls
# MISTRAL_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY add the Mistral and GPT-Luna live tests
ruff check . && ruff format --check .
python benchmarks/scanned_books/run.py --backend datalab --mode accurate  # real API, ~$0.12
```

- `tests/conftest.py` provides `FakeBackend` (synchronous in-memory backend for pipeline tests), `FakeClient` (stand-in for `DatalabClient`), a `CapturingConsole` and an `examples` fixture that copies the alice and equations PDFs.
- `test_pipeline.py` tests orchestration with `FakeBackend`. `test_datalab_backend.py` tests Datalab request fields, polling, resubmits and timeouts through the pipeline with `FakeClient`. `test_openai_backend.py` tests both GPT-Luna routes with `FakeResponses`: request bodies, page joining, page-count retries and the page-by-page fallback and cost. `test_mistral_backend.py` tests Mistral with `FakeOCR`: request bodies, page selection, images, tables, footnotes from the header and footer and cost.
- `tests/samples.py` lists every sample PDF in `examples/` with its page count, language, required keywords, image expectation, challenge, reference-output mode and minimum table rows. `test_samples.py` checks the PDFs and committed reference outputs offline. `test_live.py` (Datalab), `test_live_mistral.py` (Mistral OCR) and `test_live_llm.py` (GPT-Luna via OpenAI and OpenRouter) convert them for real. Live tests use the `live` marker, are deselected by default and skip when their service's key is absent.
- `test_cli.py`, `test_discovery.py`, `test_pdf.py`, `test_spreads.py`, `test_assemble.py`, `test_markdown.py` and `test_console.py` cover the corresponding local behavior offline. Changes to spread splitting or output normalization need these checks as well as backend tests.
- `benchmarks/scanned_books/`: 16 public-domain PDF pages with `reference/` transcriptions, `manifest.py` (samples and spelling probes), `score.py` (word accuracy, footnotes, spelling probes, spread order), `run.py` (converts with this checkout and scores), `build_samples.py` (rebuilds PDFs from the Internet Archive) and saved `baselines/`. `run.py --out DIR` retains results; arguments after `--` pass through to the CLI. Use the existing baseline directory names: `<backend>-<mode>`, `mistral` without a mode and a `-split-spreads` suffix for split runs. When regenerating a baseline or correcting a reference, re-score affected outputs and update `tests/test_benchmark.py::EXPECTED`, the benchmark README table and any affected figures in `docs/ocr-models.md` or `HOW-IT-WORKS.md`.
- HTTP behavior is tested with `FakeSession`/`FakeResponse` from `conftest.py` in `tests/test_datalab_client.py`, `tests/test_mistral_client.py` and `tests/test_openai_client.py`.
- To add a backend: subclass `Backend` under `backends/<name>/`, give it a `BackendInfo`, register it in `BACKENDS` and emit `ChunkOutput` content in Marker's conventions so `assemble()` can merge it.
- CI (`ci.yml`) runs lint, tests on Linux (Python 3.11-3.14), macOS and Windows (3.13) and a wheel smoke test. `live.yml` runs the live suite on manual dispatch using the `DATALAB_API_KEY` secret, plus optional `MISTRAL_API_KEY`, `OPENAI_API_KEY` and `OPENROUTER_API_KEY` secrets.

## Documentation rules for agents

- Update docs with behavior changes: usage in `README.md`, internals in `HOW-IT-WORKS.md`, release notes under `CHANGELOG.md`'s Unreleased heading and this guide when the implementation map or conventions change.
- Keep the README focused on using the tool: concise description, installation, then usage and reference material. Keep backend comparisons and API-key setup in one place; link to detailed model research and runtime internals instead of copying them into the README.
- Use plain, factual prose, sentence-case headings and no promotional feature lists, canned transitions or repeated summaries. Follow the [writing rules](https://github.com/SokolskyNikita/misc-scripts/blob/main/ai-context-files/ai-humanlike-writing-rules.md), except its citation/attribution rules. Use straight quotes and omit serial commas.
- The README is also the PyPI page, so use absolute GitHub URLs for repository links. Keep its sample list selective; `examples/README.md` owns the full list and provenance.
- `examples/` pairs sample PDFs with generated Datalab outputs. Never hand-edit those outputs. Regenerate each PDF separately with `--backend datalab --overwrite`, adding `--mode` when its `tests/samples.py` entry sets one; the CLI cannot apply different modes within one directory run. The 1880 census and Lane lexicon require `accurate`. Add only public-domain excerpts from legitimate sources and record their provenance.
- Releases: move Unreleased notes under a dated version heading, bump `pyproject.toml`, commit and push `main`, then wait for CI. Push an annotated `vX.Y.Z` tag matching the package version. `.github/workflows/release.yml` checks that match, runs tests, builds the package, creates the GitHub release from the changelog and publishes to PyPI via Trusted Publishing.
