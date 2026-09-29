<h1 align="center">pdf-to-md</h1>

<p align="center">
  <strong>Turn PDFs, scans, and Office documents into clean Markdown with one command, even 1,000-page books.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/pdf-to-markdown-cli/"><img src="https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/pdf-to-markdown-cli/"><img src="https://img.shields.io/pypi/pyversions/pdf-to-markdown-cli.svg" alt="Python versions"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml"><img src="https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/releases"><img src="https://img.shields.io/github/v/release/SokolskyNikita/pdf-to-markdown-cli" alt="GitHub release"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>

`pdf-to-md` is a command-line tool that converts documents to Markdown, HTML, or JSON with the [Datalab](https://www.datalab.to/) Convert API, the hosted version of the open-source [Marker](https://github.com/datalab-to/marker) engine. It handles the tedious parts for you: splitting big PDFs, uploading in parallel, retrying, stitching the results back together, and fixing page numbers and image links.

```console
$ pdf-to-md books/
✓ darwin_origin_of_species_1859.pdf → darwin_origin_of_species_1859.md (516 pages, $1.55)
✓ tolstoy_voina_i_mir_t1_1937.pdf → tolstoy_voina_i_mir_t1_1937.md (537 pages, $1.61)
✓ grimm_kinder_und_hausmaerchen_1857.pdf → grimm_kinder_und_hausmaerchen_1857.md (510 pages, $1.53)
Done in 4m37s: 3 converted · 1563 pages · $4.69
```

<sub>Output from a real run (file names shortened): three scanned 19th-century books in English, Russian, and German Fraktur.</sub>

## Why pdf-to-md

- **Built for big documents.** PDFs are split into page chunks that convert in parallel and are merged back into a single file. Page separators, anchors, and image links stay correct across chunks.
- **Safe to re-run.** Output names are deterministic (`report.pdf` → `report.md`) and finished files are skipped. Re-running on a folder converts only what's new or failed, so you never pay twice by accident.
- **Honest about results.** Every file reports its pages and cost. The exit code says whether anything failed. A bad API key stops the run immediately instead of failing file by file.
- **Resilient.** Rate limits, server errors, and dropped connections are retried with backoff. Ctrl-C stops cleanly without leaving half-written files.
- **Made for scripting.** Converted paths go to stdout, progress and errors to stderr, so it drops straight into pipelines and CI jobs.
- **Any language, any era.** Tested on modern PDFs, math, and scans of Cyrillic, blackletter German, and vertical classical Chinese ([samples](#sample-conversions)).

## Installation

Requires Python 3.10 or newer.

```bash
pipx install pdf-to-markdown-cli        # recommended: isolated install
uv tool install pdf-to-markdown-cli     # or with uv
pip install pdf-to-markdown-cli         # or into the current environment
```

Then get an API key from [datalab.to/app/keys](https://www.datalab.to/app/keys) and export it:

```bash
export DATALAB_API_KEY="your_api_key"
```

## Quick start

```bash
pdf-to-md report.pdf
```

This writes `report.md` next to the PDF, plus a `report_images/` folder if the document contains images. That's it.

## Recipes

```bash
# Convert a whole folder tree into a separate output folder, keeping its structure
pdf-to-md ~/papers -o ~/papers-md

# Preview what would happen (files, pages, chunks) without spending credits
pdf-to-md ~/papers --dry-run

# Best quality for difficult scans, tables, and handwriting
pdf-to-md scan.pdf --mode accurate

# Only some pages (0-based, like the API): the first ten plus page 42
pdf-to-md book.pdf --page-range 0-9,42

# HTML or JSON instead of Markdown
pdf-to-md slides.pptx --html
pdf-to-md form.pdf --json

# Keep page boundaries visible in the output
pdf-to-md contract.pdf --paginate

# Text only: no image files, no generated image descriptions
pdf-to-md manual.pdf --no-images --no-image-captions

# Redo everything, replacing earlier outputs
pdf-to-md ~/papers --overwrite

# Use the converted files in a pipeline
pdf-to-md ~/papers -q | xargs wc -w
```

## How it works

```mermaid
flowchart LR
    A[Inputs: files and folders] --> B[Plan outputs<br/>skip finished files]
    B --> C[Split PDFs into<br/>page chunks]
    C --> D[Upload chunks<br/>in parallel]
    D --> E[Poll with backoff<br/>retry transient errors]
    E --> F[Merge in page order<br/>renumber pages, rename images]
    F --> G[Write atomically<br/>report.md + report_images/]
```

1. **Plan.** Inputs are discovered recursively. Hidden files and folders this tool generated earlier are ignored. Each input gets a deterministic output path, and inputs whose output already exists are skipped.
2. **Split.** PDFs are cut into chunks of `--chunk-size` pages (default 25). Page selection with `--page-range` or `--max-pages` happens here, so only those pages are uploaded and billed. Other formats are uploaded whole.
3. **Convert.** Up to `--concurrency` chunks (default 5) are processed at once. Each one is uploaded and then polled until it's done. Throttling and server errors are retried, honoring the API's `Retry-After`.
4. **Merge.** Chunk results are joined in page order. Page separators, HTML page ids, JSON block ids, and in-document anchors are renumbered to match the original document. Images are renamed so they never collide, and links to them are URL-encoded.
5. **Write.** The output is written to a temporary file and renamed into place, so an interrupted run never leaves a partial file behind.

## Output

```text
papers/
├── report.pdf
├── report.md          ← converted document
└── report_images/     ← extracted images (only if there are any)
```

- If two inputs would produce the same name (`a.pdf` and `a.docx`), both keep their source extension: `a.pdf.md` and `a.docx.md`. Names are compared case-insensitively, and an output never overwrites an input.
- Hard-wrapped paragraph lines are joined in Markdown output (disable with `--keep-line-breaks`). Image descriptions live in the image alt text.

## Supported formats

| Input | Extensions |
| --- | --- |
| PDF | `.pdf` (split into chunks) |
| Word processing | `.doc` `.docx` `.odt` |
| Presentations | `.ppt` `.pptx` `.odp` |
| Spreadsheets | `.xls` `.xlsx` `.xlsm` `.xltx` `.ods` `.csv` |
| Web and ebooks | `.html` `.htm` `.epub` |
| Images | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.tiff` `.tif` |

Outputs are Markdown (`.md`, the default), HTML (`.html`), or JSON (`.json`, Marker's block tree with page and position data). The API accepts files of up to 200 MB. Non-PDF files are always sent as a single request.

## Quality, speed, and cost

`--mode` picks a Datalab processing mode:

| Mode | Use it for |
| --- | --- |
| `fast` (API default) | Clean digital PDFs and good scans. |
| `balanced` | Mixed documents with tables, forms, or harder layouts. |
| `accurate` | The hardest material: poor scans, dense tables, handwriting. |

Every result line shows what Datalab billed, and the run summary adds it up. In our September 2026 test runs, conversions cost about 0.3¢ per page ($3 per 1,000 pages). See [Datalab's pricing](https://www.datalab.to/pricing) for current rates.

Throughput depends on your plan's limits. With the default of 5 concurrent requests (the free tier's limit), the 1,563-page run above took 4 minutes 37 seconds. Paid plans allow far more concurrency, so raise `-j` to match yours.

## Sample conversions

[`examples/`](https://github.com/SokolskyNikita/pdf-to-markdown-cli/tree/main/examples) holds sample documents next to their actual output from this tool:

| Sample | Language | What it tests | Output |
| --- | --- | --- | --- |
| Alice in Wonderland | English | Illustrated novel, curly quotes | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/alice_in_wonderland_sample.md) |
| Algebraic geometry notes | English | Mathematics rendered as LaTeX | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/equations.md) |
| *On the Origin of Species* (1859) | English | Old scan with the fold-out tree diagram | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/darwin_origin_of_species_en.md) |
| *War and Peace*, 1937 edition | Russian | Cyrillic mixed with French, footnotes, margin line numbers | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/tolstoy_war_and_peace_ru.md) |
| *Kinder- und Hausmärchen* (1857) | German | Fraktur blackletter typeface | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/grimm_fairy_tales_de.md) |
| *Shijing Gupu* (1908) | Chinese | Vertical right-to-left text and music notation | [Markdown](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/shijing_gupu_zh.md) |

See [examples/README.md](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/README.md) for sources and how the samples are used in tests.

## Command reference

```text
pdf-to-md INPUT [INPUT ...] [options]
```

`INPUT` is any mix of files and directories. The tool also runs as `python -m docs_to_md`.

**Output**

| Option | Description |
| --- | --- |
| `-f`, `--format {markdown,html,json}` | Output format. Default: `markdown`. `--html` and `--json` are shortcuts. |
| `-o`, `--output-dir DIR` | Write here instead of next to each input. Folder structure under directory inputs is mirrored. |
| `--overwrite` | Replace existing outputs instead of skipping those inputs. |
| `--keep-line-breaks` | Keep hard-wrapped paragraph lines in Markdown. |

**Conversion**

| Option | Description |
| --- | --- |
| `-m`, `--mode {fast,balanced,accurate}` | Quality versus speed and cost. Default: the API's (`fast`). |
| `--paginate` | Insert page separators. |
| `--no-images` | Don't extract images. |
| `--no-image-captions` | Don't generate image descriptions. |
| `--skip-cache` | Ignore Datalab's server-side cache of previous results. |
| `--api-option KEY=VALUE` | Send any other [Convert API](https://documentation.datalab.to/api-reference/convert-document) field. Repeatable, e.g. `--api-option extras=extract_links`. |

**Pages and chunking**

| Option | Description |
| --- | --- |
| `--page-range RANGE` | 0-based pages to convert, e.g. `0,5-10`. |
| `--max-pages N` | Convert at most `N` pages of each document. |
| `--chunk-size N` | PDF pages per request. Default: `25`. Smaller chunks mean more parallelism but more requests. |
| `--no-chunk` | Send each PDF as one request. |

**Run control**

| Option | Description |
| --- | --- |
| `--api-key KEY` | API key. Prefer the environment variable, which keeps the key out of shell history. |
| `-j`, `--concurrency N` | Requests in flight at once. Default: `5`. |
| `--timeout SECONDS` | Give up on a single request after this long. Default: `3600`. |
| `-n`, `--dry-run` | Show what would be converted, with page and chunk counts. Makes no API calls and needs no key. |
| `-q`, `--quiet` | Print only errors (converted paths still go to stdout). |
| `-v`, `--verbose` | Print debug logs, including every API call and retry. |
| `--version` | Print the version and exit. |

## Scripting and automation

Only converted file paths are printed to stdout, one per line. Status lines, the progress bar, and errors go to stderr.

| Exit status | Meaning |
| --- | --- |
| `0` | Every input was converted or skipped. |
| `1` | At least one file failed; the rest were still converted. |
| `2` | Usage or configuration error, including a rejected API key or an exhausted account. |
| `130` | Interrupted with Ctrl-C. |

Because finished files are skipped, the simplest way to retry failures in an interrupted batch is to run the same command again.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATALAB_API_KEY` | API key, the same variable Datalab's official SDK uses. `MARKER_PDF_KEY` (from versions before 1.0) also works. `--api-key` takes precedence over both. |
| `NO_COLOR` | Disable colored output. |

The tool keeps no state between runs. Temporary chunk files live in the system temp directory and are deleted when the run ends.

## Troubleshooting

| Message | What to do |
| --- | --- |
| `No API key found` | Set `DATALAB_API_KEY`. |
| `Authentication failed` | The key was rejected. Check it on the [Datalab dashboard](https://www.datalab.to/app/keys). |
| `Payment required` | Your Datalab account is out of credits. |
| `... exists (use --overwrite)` | The output is already there. Add `--overwrite` to redo it. |
| `timed out` | A request took longer than `--timeout`. Raise it, or lower `--chunk-size`. |
| Frequent throttling | You're above your plan's limits (the free tier allows 10 requests per minute). Lower `-j`. |

Anything else: rerun with `-v` and [open an issue](https://github.com/SokolskyNikita/pdf-to-markdown-cli/issues) with the output.

## Upgrading from 0.x

Version 1.0 moved to Datalab's current `/api/v1/convert` endpoint and fixed `--html` and `--json`, which produced no output in 0.5.x.

- Outputs are now `report.md` + `report_images/` instead of `report_<random>.md` + `images_<random>/`, and existing outputs are skipped unless you pass `--overwrite`.
- `-o` accepts relative paths and mirrors folder structure.
- `--llm` now means `--mode balanced` and `--max` means `--mode accurate`. Datalab removed the options behind `--strip`, `--force`, and `--langs`, so those flags are ignored with a warning.
- `--pages`, `--noimg`, `-cs`, and `-mp` still work as aliases of `--paginate`, `--no-images`, `--chunk-size`, and `--max-pages`.
- Failures now exit non-zero, and `~/.docs_to_md/` is no longer used and can be deleted.

Full details are in the [changelog](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/CHANGELOG.md).

## Contributing

Bug reports, ideas, and pull requests are welcome. [CONTRIBUTING.md](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/CONTRIBUTING.md) covers setup, the test suites (including the opt-in live API tests), and the release process.

## Acknowledgements

Conversion quality comes from [Marker](https://github.com/datalab-to/marker) and the [Datalab](https://www.datalab.to/) API. This is an independent project and isn't affiliated with Datalab.

## License

[MIT](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/LICENSE) © Nikita Sokolsky
