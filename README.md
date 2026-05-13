# PDF to Markdown CLI

[![PyPI](https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Fast command-line PDF to Markdown conversion powered by the [Datalab Marker API](https://www.datalab.to/marker).

`pdf-to-md` is built for people who need reliable Markdown output from PDFs, including long books, reports, papers, scans, and directories full of source documents. It can split large PDFs into smaller page chunks, submit those chunks as separate Marker jobs, poll until they finish, and stitch the results back into one output file.

The result: less waiting on one giant conversion, fewer failures on large files, and a repeatable CLI workflow you can run from any shell.

## Why use this tool

- Convert PDFs to Markdown with one command.
- Handle giant PDFs efficiently by chunking pages and merging the finished output.
- Process a single file or recursively convert supported files in a directory.
- Keep extracted images with the generated Markdown and rewrite image links automatically.
- Choose Markdown by default, or request JSON/HTML when you need structured output.
- Use Marker OCR and enhancement options without writing API polling code yourself.

## Quick start

Install:

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

Convert a large PDF with smaller chunks:

```bash
pdf-to-md ./huge-report.pdf --chunk-size 10
```

Convert every supported file in a directory:

```bash
pdf-to-md ./docs
```

Markdown is the default output. Use `--json` or `--html` when you want another Marker output format:

```bash
pdf-to-md ./examples/equations.pdf --json
pdf-to-md ./examples/equations.pdf --html
```

You can also run the package as a module:

```bash
python -m docs_to_md ./examples/equations.pdf
```

## Built for large PDFs

Large PDFs are where this CLI is most useful.

By default, PDFs are split into 25-page chunks before submission. Each chunk is submitted to Marker, tracked independently, and written to a temporary result file when complete. Once all chunks finish, the CLI combines them in page order into a single `.md`, `.json`, or `.html` file.

You can tune the chunk size:

```bash
pdf-to-md ./book.pdf --chunk-size 15
```

Or send a PDF as one practical unit:

```bash
pdf-to-md ./book.pdf --no-chunk
```

Chunking helps long conversions finish more reliably because each Marker request handles a smaller page range, while the CLI takes care of polling and final assembly.

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

When images are returned, Markdown image links are rewritten to point at the generated image directory.

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

## Examples

Run OCR in multiple languages:

```bash
pdf-to-md ./paper.pdf --langs "English,French"
```

Use Marker LLM enhancement:

```bash
pdf-to-md ./paper.pdf --llm
```

Force OCR on every page:

```bash
pdf-to-md ./scan.pdf --force
```

Use all high-quality OCR enhancement flags together:

```bash
pdf-to-md ./scan.pdf --max
```

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
