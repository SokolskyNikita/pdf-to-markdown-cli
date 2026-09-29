# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to `pdf-to-markdown-cli` are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html), and this file follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.0.0] - 2026-09-29

First stable release: a rewrite on Datalab's current Convert API with a scriptable, re-runnable CLI. See "Upgrading from 0.x" in the README.

### Added

- `--mode {fast,balanced,accurate}`, `--page-range`, `--no-image-captions`, `--skip-cache`, and `--api-option KEY=VALUE` for any other Convert API field.
- Multiple inputs per command, e.g. `pdf-to-md a.pdf b.docx docs/`.
- `--dry-run` previews files, pages, and chunks without calling the API or needing a key.
- `--overwrite`: existing outputs are now skipped by default, so re-runs only convert what's new.
- `-j/--concurrency`: chunks and files convert in parallel (default 5).
- `--timeout`, `-q/--quiet`, `--keep-line-breaks`, and `--api-key`.
- The `DATALAB_API_KEY` environment variable, matching Datalab's official SDK. `MARKER_PDF_KEY` still works.
- Input types: `.xlsm`, `.xltx`, `.csv`, `.htm`, `.tif`.
- A per-file result line and an end-of-run summary with page count and cost. Converted paths are printed to stdout.
- Markdown paragraphs that were hard-wrapped are joined (disable with `--keep-line-breaks`).
- Markdown no longer repeats each generated image description as a paragraph under the image. The description stays in the alt text.

### Changed

- Uses `POST /api/v1/convert`; the `/api/v1/marker` endpoint is deprecated upstream.
- Deterministic output names: `report.md` + `report_images/` instead of UUID-keyed names. Same-name inputs become `a.pdf.md` / `a.docx.md`, and other clashes get a numeric suffix. Names are compared case-insensitively, and an output never overwrites an input file.
- `-o/--output-dir` accepts relative paths and mirrors the input folder tree.
- `--llm` now means `--mode balanced` and `--max` means `--mode accurate`. `--strip`, `--force`, and `--langs` are ignored with a warning because the API removed them. `--pages`, `--noimg`, `-cs`, and `-mp` are still accepted as aliases of the new flag names.
- Exit codes: `0` success, `1` some files failed, `2` usage/auth error, `130` interrupted.
- Quieter default output. Timestamps and debug logs only appear with `-v`.
- Dependencies trimmed to `requests`, `pikepdf`, and `tqdm`.
- Flat package layout and a pytest suite with 97% branch coverage. CI runs ruff, tests on Python 3.10-3.14, and a packaging check.

### Fixed

- `--html` and `--json` produced no output, because the response fields were misnamed.
- Failures (including an invalid API key) exited `0` and printed "Conversion completed successfully".
- `--max-pages` was applied to every chunk instead of the whole document.
- Retries never happened because the client swallowed exceptions. 429/5xx/network errors now retry with backoff and honor `Retry-After`.
- Long conversions were marked failed after about 5 minutes of polling.
- A 30-second request timeout broke uploads of large files.
- Re-running on a directory re-converted previously extracted images, and `--html` could overwrite `.html` inputs.
- Page separators, JSON block ids, and image names restarted in every chunk. Image links broke on filenames with spaces.
- Ctrl-C printed a traceback and left temporary files behind.

### Removed

- The on-disk request cache (`~/.docs_to_md/`), which was never reused between runs.
- The copied documentation for the deprecated Marker endpoint. The docs now link to the live Datalab API reference.

## [0.5.2] - 2026-05-13

### Added

- Fallback handling when the default cache or temp directories are not writable.
- Test coverage for HTML output CLI configuration.
- Mocked test coverage for processing both bundled example PDFs.
- CI and dependency automation configuration in `.github/workflows/ci.yml` and `.github/dependabot.yml`.

### Changed

- Expanded supported input extension and MIME mappings for documents, spreadsheets, presentations, web/ebook files, and images.
- Improved result polling with per-chunk exponential backoff and cleaner progress handling.
- Modernized packaging and project metadata in `pyproject.toml`.
- Refreshed public and contributor documentation.

### Fixed

- Avoided false "unsupported file type" failures by adding MIME detection fallbacks.
- Fixed a cache retrieval edge case where empty payloads were treated as missing.
- Improved request/chunk state tracking for completion and failure handling.

## [0.5.1] - 2025-09-29

### Fixed

- Prevented creation of output image directories when no images were returned.
- Corrected generated filename and image path handling for output assets.

## [0.5.0] - 2025-05-19

### Added

- Unit test coverage for CLI processing paths.

### Changed

- Updated project docs for Datalab Marker API usage and contributor workflow.
- Refactored processor internals into clearer chunking and submission helper flows.
- Switched test execution to `unittest`.

### Fixed

- Fixed mutable default list behavior in request/chunk models.

## [0.4.0] - 2025-04-21

### Changed

- Polished post-refactor processing behavior and output handling for the package layout.

### Fixed

- Improved image path deduplication and related output consistency.

## [0.3.0] - 2025-04-19 (unpublished)

### Changed

- Refactored processing, caching, and result handling internals.

## [0.2.1] - 2025-04-10

### Fixed

- Fixed packaging and distribution issues from the first PyPI release.

## [0.2.0] - 2025-04-10

### Added

- First public PyPI release of `pdf-to-markdown-cli`.
- Package and distribution scaffolding for pip installation and the `pdf-to-md` CLI entrypoint.

### Changed

- Reorganized the project into a publishable Python package.
