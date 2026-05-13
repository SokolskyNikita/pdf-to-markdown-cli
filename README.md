# PDF to markdown CLI

[![PyPI](https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Command-line utility for converting PDFs and other supported documents into Markdown, JSON, or HTML using the [Marker API](https://www.datalab.to/marker).

## Why use this tool

- Converts single files or entire directories
- Automatically splits large PDFs into chunks and merges results
- Persists request state locally so interrupted runs can recover
- Rewrites and copies extracted images into deterministic output folders
- Supports OCR/LLM tuning flags from the Marker API

## Supported formats

### Input

- PDF (`.pdf`)
- Word (`.doc`, `.docx`, `.odt`)
- PowerPoint (`.ppt`, `.pptx`, `.odp`)
- Spreadsheets (`.xls`, `.xlsx`, `.ods`)
- EPUB/HTML (`.epub`, `.html`)
- Images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`)

### Output

- Markdown (`.md`, default)
- JSON (`.json`)
- HTML (`.html`)

## Installation

```bash
pip install pdf-to-markdown-cli
```

From source:

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git
cd pdf-to-markdown-cli
pip install -e .
```

## Quick start

```bash
export MARKER_PDF_KEY="your_api_key"
pdf-to-md ./examples/equations.pdf
```

Process a directory:

```bash
pdf-to-md ./docs
```

Use JSON or HTML output:

```bash
pdf-to-md ./examples/equations.pdf --json
pdf-to-md ./examples/equations.pdf --html
```

## CLI options

- `input`: input file or directory path
- `--json`: output JSON instead of Markdown
- `--html`: output HTML instead of Markdown
- `--langs`: comma-separated OCR languages (default: `English`)
- `--llm`: enable LLM-enhanced processing
- `--strip`: redo OCR
- `--noimg`: disable image extraction
- `--force`: force OCR on all pages
- `--pages`: include page delimiters
- `--max`: enable all OCR enhancement flags (`--llm --strip --force`)
- `-mp`, `--max-pages`: process only the first N pages
- `--no-chunk`: disable PDF chunking
- `-cs`, `--chunk-size`: PDF pages per chunk (default: `25`)
- `-o`, `--output-dir`: absolute output directory path
- `-v`, `--verbose`: debug logging
- `--version`: show installed package version

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

For contributions or questions, open a GitHub issue.
