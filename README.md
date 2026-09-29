# PDF to Markdown CLI

[![PyPI](https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![GitHub release](https://img.shields.io/github/v/release/SokolskyNikita/pdf-to-markdown-cli)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/releases)
[![Python versions](https://img.shields.io/pypi/pyversions/pdf-to-markdown-cli.svg)](https://pypi.org/project/pdf-to-markdown-cli/)
[![CI](https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`pdf-to-md` converts PDFs, Office documents, ebooks, and images to Markdown, HTML, or JSON using the [Datalab](https://www.datalab.to/) Convert API (the hosted version of [Marker](https://github.com/datalab-to/marker)).

It is built for large documents and whole folders:

- **Big PDFs, fast.** PDFs are split into page chunks that convert in parallel and are stitched back into one file, with page numbers and image links fixed up across chunks.
- **Safe to re-run.** Output names are deterministic (`report.pdf` → `report.md`) and existing outputs are skipped, so re-running a folder only converts what is new. You never pay twice by accident.
- **Scriptable.** Converted file paths go to stdout, progress to stderr, and exit codes tell you what happened.
- **Resilient.** Rate limits, server errors, and dropped connections are retried with backoff. A bad API key stops the run immediately instead of failing file by file.

## Quick start

```bash
pip install pdf-to-markdown-cli     # or: pipx install pdf-to-markdown-cli
export DATALAB_API_KEY="your_api_key"   # https://www.datalab.to/app/keys
pdf-to-md report.pdf
```

```text
✓ report.pdf → report.md (48 pages, $0.14)
report.md
```

## Usage

```bash
pdf-to-md INPUT [INPUT ...] [options]
```

`INPUT` can be any mix of files and directories. Directories are searched recursively. Hidden files and image folders this tool generated are skipped.

```bash
pdf-to-md report.pdf                   # → report.md + report_images/
pdf-to-md docs/ -o converted/          # mirror a folder tree into converted/
pdf-to-md *.docx --html                # HTML output
pdf-to-md scan.pdf --mode accurate     # highest quality: slower and more expensive
pdf-to-md book.pdf --page-range 0-9    # first ten pages (0-based, like the API)
pdf-to-md docs/ --dry-run              # preview files, pages, and chunks; no API calls
pdf-to-md docs/ --overwrite            # redo everything, replacing old outputs
```

The package can also run as a module: `python -m docs_to_md report.pdf`.

Sample outputs live in [`examples/`](examples/): each PDF sits next to its converted `.md` file and images folder.

## Options

### Output

| Option | Description |
| --- | --- |
| `-f`, `--format {markdown,html,json}` | Output format. Default: `markdown`. `--html` and `--json` are shortcuts. |
| `-o`, `--output-dir DIR` | Write outputs here instead of next to each input. Subfolders of directory inputs are mirrored. |
| `--overwrite` | Replace existing outputs. Without it, inputs whose output already exists are skipped. |
| `--keep-line-breaks` | Keep hard-wrapped paragraph lines in Markdown. By default they are joined. |

### Conversion

| Option | Description |
| --- | --- |
| `-m`, `--mode {fast,balanced,accurate}` | Quality versus speed and cost. When omitted, the API default (`fast`) is used. |
| `--paginate` | Insert page separators. Page numbers stay correct across chunks. |
| `--no-images` | Don't extract images. |
| `--no-image-captions` | Don't generate text descriptions of images. |
| `--skip-cache` | Ignore Datalab's server-side result cache. |
| `--api-option KEY=VALUE` | Pass any other [Convert API](https://documentation.datalab.to/api-reference/convert-document) field, e.g. `--api-option extras=extract_links`. Repeatable. |

### Pages and chunking

| Option | Description |
| --- | --- |
| `--page-range RANGE` | 0-based pages to convert, e.g. `0,5-10`. |
| `--max-pages N` | Convert at most `N` pages of each document. |
| `--chunk-size N` | PDF pages per API request. Default: `25`. |
| `--no-chunk` | Send each PDF as a single request. |

For PDFs, page selection happens locally before splitting, so only the requested pages are uploaded and billed.

### Run control

| Option | Description |
| --- | --- |
| `--api-key KEY` | API key. Prefer the `DATALAB_API_KEY` environment variable so the key stays out of shell history. |
| `-j`, `--concurrency N` | Requests in flight at once. Default: `5`, the free tier's concurrency limit. |
| `--timeout SECONDS` | Give up on a single request after this long. Default: `3600`. |
| `-n`, `--dry-run` | List what would be converted, with page and chunk counts. Makes no API calls and needs no key. |
| `-q`, `--quiet` / `-v`, `--verbose` | Show only errors, or show debug logs. |
| `--version` | Print the version. |

## Output files

```text
docs/report.pdf
docs/report.md             # converted document
docs/report_images/        # extracted images, created only if there are any
```

- Image links in the output point into the images folder and are URL-encoded, so names with spaces work.
- If two inputs share a name (`a.pdf` and `a.docx`), both keep their source extension: `a.pdf.md` and `a.docx.md`.
- Outputs are written atomically. An interrupted or failed conversion never leaves a half-written file behind.

## Supported inputs

| Type | Extensions |
| --- | --- |
| PDF | `.pdf` |
| Word processing | `.doc`, `.docx`, `.odt` |
| Presentations | `.ppt`, `.pptx`, `.odp` |
| Spreadsheets | `.xls`, `.xlsx`, `.xlsm`, `.xltx`, `.ods`, `.csv` |
| Web and ebooks | `.html`, `.htm`, `.epub` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`, `.tif` |

Only PDFs are split into chunks. Other files are uploaded as-is. The API accepts uploads of up to 200 MB.

## Scripting

Converted paths are printed to stdout, one per line. Everything else goes to stderr:

```bash
pdf-to-md papers/ -q | xargs wc -w
```

| Exit status | Meaning |
| --- | --- |
| `0` | Every file was converted or skipped. |
| `1` | At least one file failed. The others were still converted. |
| `2` | Usage or configuration error, including a rejected API key or no credits. |
| `130` | Interrupted with Ctrl-C. |

Set `NO_COLOR=1` to disable colored output.

## Configuration

The API key is read from, in order: `--api-key`, `DATALAB_API_KEY`, and `MARKER_PDF_KEY` (the name used before 1.0). Get a key at [datalab.to/app/keys](https://www.datalab.to/app/keys).

The CLI keeps no state between runs. Temporary chunk files live in the system temp directory and are removed when the run ends.

## Upgrading from 0.x

Version 1.0 moves to Datalab's current `/api/v1/convert` endpoint and fixes `--html` and `--json` output, which failed in 0.5.x. Behavior changes:

- **Output names are deterministic.** You now get `report.md` and `report_images/` instead of `report_<random>.md` and `images_<random>/`. Existing outputs are skipped unless you pass `--overwrite`.
- **`-o` accepts relative paths** and mirrors subfolders when converting a directory.
- **Quality flags follow the API.** `--llm` maps to `--mode balanced` and `--max` to `--mode accurate`. Datalab removed the options behind `--strip`, `--force`, and `--langs`, so those flags are accepted but ignored, with a warning.
- **Renamed flags:** `--pages` → `--paginate`, `--noimg` → `--no-images`, `-cs` → `--chunk-size`, `-mp` → `--max-pages`. The old spellings still work.
- **Exit codes are meaningful.** Failures now exit non-zero instead of reporting success.
- **No local cache.** `~/.docs_to_md/` is no longer used and can be deleted.

## Troubleshooting

- **`No API key found`**: set `DATALAB_API_KEY`.
- **`Authentication failed`**: the key was rejected. Check it on the Datalab dashboard.
- **`Payment required`**: your Datalab account is out of credits.
- **`... exists (use --overwrite)`**: the output is already there. Pass `--overwrite` to redo it.
- **`timed out`**: a request took longer than `--timeout`. Raise it, or lower `--chunk-size`.
- **Frequent rate limiting on the free tier**: lower `-j/--concurrency`. The free tier allows 10 requests per minute.
- Run with `-v` to see every API call and retry.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git
cd pdf-to-markdown-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest --cov
ruff check . && ruff format --check .
```

## License

[MIT](LICENSE)
