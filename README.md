# PDF to Markdown CLI

[![PyPI](https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`pdf-to-md` converts PDFs and other document files to Markdown, JSON, or HTML through the [Datalab Marker API](https://www.datalab.to/marker).

It is a small CLI wrapper around the `docs_to_md` Python package. It handles local file discovery, PDF chunking, API submission, polling, output file naming, extracted images, and temporary/cache cleanup.

## Quick start

Install the package:

```bash
pip install pdf-to-markdown-cli
```

Set your Datalab API key:

```bash
export MARKER_PDF_KEY="your_api_key"
```

Convert one file:

```bash
pdf-to-md ./examples/equations.pdf
```

Convert every supported file under a directory:

```bash
pdf-to-md ./docs
```

The default output is Markdown. Use `--json` or `--html` to request another Marker output format:

```bash
pdf-to-md ./examples/equations.pdf --json
pdf-to-md ./examples/equations.pdf --html
```

You can also run the package as a module:

```bash
python -m docs_to_md ./examples/equations.pdf
```

## What the CLI does

- Accepts either a single input file or a directory.
- Recursively scans directories for supported extensions.
- Splits PDFs larger than the configured chunk size, submits each chunk, and combines completed chunks in order.
- Sends Marker options such as OCR language, LLM enhancement, forced OCR, pagination, and maximum pages.
- Stores in-flight request/chunk state in a local disk cache while processing.
- Writes output files with a short unique suffix to avoid collisions.
- Saves extracted images only when Marker returns images, then rewrites Markdown image references to the final image folder.

## Supported formats

Input file extensions:

- PDF: `.pdf`
- Word: `.doc`, `.docx`, `.odt`
- PowerPoint: `.ppt`, `.pptx`, `.odp`
- Spreadsheets: `.xls`, `.xlsx`, `.ods`
- Web and ebook: `.html`, `.epub`
- Images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

Output formats:

- Markdown: `.md` by default
- JSON: `.json` with `--json`
- HTML: `.html` with `--html`

## Output paths

By default, output files are written next to the input file. When `-o` or `--output-dir` is provided, it must be an absolute directory path.

Each conversion receives a short unique key:

```text
input.pdf
input_a1b2c3d4.md
images_a1b2c3d4/
```

The image directory is created only when the Marker result includes images. If no images are returned, no empty image directory is left behind.

## CLI reference

Required argument:

- `input`: input file or directory path.

Output options:

- `--json`: request JSON output.
- `--html`: request HTML output.
- `-o`, `--output-dir`: absolute output directory path. Defaults to the input file's directory.

Marker processing options:

- `-l`, `--langs`: comma-separated OCR languages. Default: `English`.
- `--llm`: enable Marker LLM enhancement.
- `--strip`: strip existing OCR and redo OCR.
- `--force`: force OCR on all pages.
- `--pages`: add page delimiters.
- `--noimg`: disable image extraction.
- `-mp`, `--max-pages`: process only the first `N` pages.
- `--max`: shorthand for `--llm --strip --force`.

Chunking and diagnostics:

- `-cs`, `--chunk-size`: PDF pages per chunk. Default: `25`.
- `--no-chunk`: disable practical chunking by using a very large chunk size.
- `-v`, `--verbose`: enable debug logging.
- `--version`: print the installed package version.

## Configuration and local state

The CLI requires `MARKER_PDF_KEY`. Get an API key from [Datalab](https://www.datalab.to/app/keys).

Local state is stored under `~/.docs_to_md/` by default:

- `~/.docs_to_md/cache`: disk cache for conversion request state.
- `~/.docs_to_md/tmp`: temporary chunk and intermediate output files.

If either directory is not writable, the CLI falls back to the system temp directory under `.docs_to_md/`.

## Development

Install from source:

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git
cd pdf-to-markdown-cli
pip install -e .
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Useful project files:

- `src/docs_to_md/config/cli.py`: command-line parsing and environment validation.
- `src/docs_to_md/core/processor.py`: file discovery, job preparation, submission, and result workflow.
- `src/docs_to_md/core/result_handler.py`: polling, chunk result saving, image rewriting, and final assembly.
- `src/docs_to_md/api/client.py`: Marker API client, MIME detection, rate limiting, and retries.
- `datalab_marker_api_docs.md`: local copy of Datalab Marker API docs for reference.

## Troubleshooting

- `Configuration error: API key not found`: set `MARKER_PDF_KEY` in your shell.
- `Output directory must be an absolute path`: pass an absolute path to `-o`.
- `No processable files found`: check the extension and make sure the file is not empty or unreadable.
- `Unsupported file type`: the extension or detected MIME type is not in the supported set.
- Processing appears slow: large PDFs may be split into many chunks and Marker processing is asynchronous.
