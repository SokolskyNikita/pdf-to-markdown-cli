# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to `pdf-to-markdown-cli` are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html), and this file follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Reworked Markdown documentation for clearer human scanning and project context.
- Clarified CLI behavior, output naming, local cache/temp state, supported formats, testing workflow, and agent guidance.

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
