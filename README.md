# PDF to Markdown CLI

Convert PDFs and other documents to Markdown using the [Marker API](https://www.datalab.to/marker).

## Features

- Convert PDFs, Word docs, PowerPoint, spreadsheets, EPUB, HTML, and images to Markdown/JSON/HTML
- Automatic chunking for large documents with parallel processing
- Progress tracking and local caching for interrupted runs
- Full OCR customization options

## Installation

### From PyPI

```bash
pip install pdf-to-markdown-cli
```

### From source

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git 
cd pdf-to-markdown-cli
pip install -e .
```

## Usage

```bash
# Get API key from https://www.datalab.to/marker
export MARKER_PDF_KEY=your_api_key_here

# Basic usage
pdf-to-md /path/to/file.pdf

# Common options
pdf-to-md /path/to/file.pdf --json          # JSON output
pdf-to-md /path/to/file.pdf --noimg         # Disable images  
pdf-to-md /path/to/file.pdf --max           # Enable all flags for maximum output quality
```

## CLI Options

- `input`: Input file or directory path
- `--json`: Output in JSON format (default is markdown)
- `--langs`: Comma-separated OCR languages (default: "English")
- `--llm`: Use LLM for enhanced processing
- `--strip`: Redo OCR processing
- `--noimg`: Disable image extraction
- `--force`: Force OCR on all pages
- `--pages`: Add page delimiters
- `--max`: Enable all OCR enhancements (equivalent to --llm --strip --force)
- `-mp`, `--max-pages`: Maximum number of pages to process from the start of the file
- `--no-chunk`: Disable PDF chunking
- `-cs`, `--chunk-size`: Set PDF chunk size in pages (default: 25)
- `-o`, `--output-dir`: Absolute path to the output directory
- `-v`, `--verbose`: Enable verbose (DEBUG level) logging
- `--version`: Show the installed version and exit

## Requirements

- Python ≥3.10
- API key from [datalab.to](https://www.datalab.to/marker)
