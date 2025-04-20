# PDF to Markdown CLI (via the Datalab Marker API)

Convert PDF files (and other documents) to Markdown using the [Marker API](https://www.datalab.to/marker) via a convenient CLI tool.

## Overview

This package provides a convenient command-line interface (`pdf-to-md`) for converting PDF files (and other document formats like Word, EPUB, images, etc.) to markdown. It leverages the Marker API for high-quality PDF conversion and handles chunking, parallel processing, and result combination.

## Features

- Convert PDFs, Word documents, PowerPoint files, spreadsheets, epub, HTML, and images to Markdown using the best-in-class Marker API by Datalab
- Handle large documents by splitting them into chunks, which massively speeds up output speed
- Progress tracking for long-running operations
- Customizable OCR options, fully reflecting Marker's API as of April 2025
- Local caching of in-progress conversions, allowing for idempotence
- Output in Markdown, JSON, or HTML format

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

### Command-line interface

```bash
# Obtain an API key by signing up on https://www.datalab.to/marker
export MARKER_PDF_KEY=your_api_key_here

# Basic usage
pdf-to-md /path/to/file.pdf

# Process all files in a directory
pdf-to-md /path/to/directory

# Output in JSON format
pdf-to-md /path/to/file.pdf --json

# Use additional languages for OCR
pdf-to-md /path/to/file.pdf --langs "English,French,German"

# Use all Marker OCR enhancements
pdf-to-md /path/to/file.pdf --max
```

### Full list of CLI options

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
- `-o`, `--output-dir`: Absolute path to the output directory. If not provided, output files will be saved in the same directory as their corresponding input files.
- `-v`, `--verbose`: Enable verbose (DEBUG level) logging

### Output Structure

By default, output files are saved in the same directory as the input file with the format `[input-filename].[format]`. For example, converting `/data/report.pdf` to markdown will result in `/data/report.md`.

If an output file with the same name already exists, the new file will be automatically renamed using a numeric suffix (e.g., `[input-filename]_1.[format]`, `[input-filename]_2.[format]`, etc.) to avoid overwriting.

If you specify `--output-dir /path/to/output`, the output file will be placed in that directory (e.g., `/path/to/output/report.md`). The same automatic renaming logic applies if a file with the same name exists in the target directory.

### API

```python
# Internal module paths remain the same
from docs_to_md.config.settings import Config
from docs_to_md.core.processor import MarkerProcessor

# Create configuration
config = Config(
    api_key="your_api_key_here",
    input_path="/path/to/file.pdf",
    output_format="markdown",
    use_llm=True
)

# Create processor and run
processor = MarkerProcessor(config)
processor.process()
```

## Project Structure

The package is organized as follows:

```
pdf-to-markdown-cli/ (Project Root)
├── docs_to_md/      (Python Package Source)
│   ├── api/
│   ├── config/
│   ├── core/
│   ├── pdf/
│   ├── storage/
│   └── utils/
├── setup.py
├── README.md
└── ... (other config files)
```

## Requirements

- Python 3.10 or higher
- Runtime dependencies are listed in `setup.py` and automatically installed via pip.
- The `requirements.txt` file lists exact versions used for development and testing, and can be used to set up a development environment: `pip install -r requirements.txt`

## Development

To run the code directly from the source tree without installation:

```bash
# Using the installed entry point (requires editable install):
# pip install -e .
# pdf-to-md /path/to/file.pdf

# Or running the module directly:
python -m docs_to_md /path/to/file.pdf 
```

For regular use after installation, use the `pdf-to-md` command.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Future Considerations

While this project currently uses a modern structure (`pyproject.toml`, `src` layout), future development might involve migrating to a standardized project template, such as [simonw/python-lib](https://github.com/simonw/python-lib), to further align with community best practices and potentially simplify workflows like automated PyPI publishing via Trusted Publishers.