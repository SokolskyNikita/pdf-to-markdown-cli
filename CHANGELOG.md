# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added fallback handling for non-writable cache/tmp directories.
- Added support tests for HTML output CLI configuration and both example PDFs.

### Changed

- Expanded supported input MIME/extension mappings for document and image formats.
- Improved result polling with per-chunk exponential backoff and cleaner logging.
- Modernized packaging and project metadata in `pyproject.toml`.

### Fixed

- Fixed false "unsupported file type" failures by adding MIME detection fallbacks.
- Fixed cache retrieval edge case where empty payloads were treated as missing.
- Fixed request state tracking semantics for completion/failure handling.
