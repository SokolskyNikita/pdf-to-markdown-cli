<h1 align="center">pdf-to-md</h1>

<p align="center">
  <strong>Turn PDFs, scans, and Office documents into clean Markdown with one command, even 1,000-page books.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/pdf-to-markdown-cli/"><img src="https://img.shields.io/pypi/v/pdf-to-markdown-cli.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/pdf-to-markdown-cli/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml"><img src="https://github.com/SokolskyNikita/pdf-to-markdown-cli/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/releases"><img src="https://img.shields.io/github/v/release/SokolskyNikita/pdf-to-markdown-cli" alt="GitHub release"></a>
  <a href="https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>

`pdf-to-md` is a command-line tool that converts documents to Markdown, HTML, or JSON with the [Datalab](https://www.datalab.to/) Convert API, the hosted version of the open-source [Marker](https://github.com/datalab-to/marker) engine. It can also read PDFs, Office files, and images with [Mistral OCR](#mistral-ocr), or transcribe PDFs and images with OpenAI's GPT-Luna, called [directly or through OpenRouter](#gpt-luna). It handles the tedious parts for you: splitting big PDFs, uploading in parallel, retrying, stitching the results back together, and fixing page numbers and image links.

```console
$ pdf-to-md books/
✓ darwin.pdf → darwin.md (516 pages, $1.55)
✓ tolstoy.pdf → tolstoy.md (537 pages, $1.61)
✓ grimm.pdf → grimm.md (510 pages, $1.53)
Done in 4m37s: 3 converted · 1563 pages · $4.69
```

<sub>Output from a real run (file names shortened): three scanned 19th-century books in English, Russian, and German Fraktur.</sub>

## Why pdf-to-md

- **Built for big documents.** PDFs are split into page chunks that convert in parallel and are merged back into a single file. Page separators, anchors, and image links stay correct across chunks.
- **Safe to re-run.** Output names are deterministic (`report.pdf` → `report.md`) and finished files are skipped. Re-running on a folder converts only what's new or failed, so you never pay twice by accident.
- **Honest about results.** Every file reports its pages and cost. The exit code says whether anything failed. A bad API key stops the run immediately instead of failing file by file.
- **Resilient.** Rate limits, server errors, and dropped connections are retried with backoff. Ctrl-C stops cleanly without leaving half-written files.
- **Made for scripting.** Converted paths go to stdout, progress and errors to stderr, so it drops straight into pipelines and CI jobs.
- **Any language, any era.** Tested on modern PDFs, math, statistical tables from a faded microfiche, and scans of Cyrillic, blackletter German, vertical classical Chinese, Arabic, Hebrew, polytonic Greek, Devanagari, and 1687 Latin ([samples](#sample-conversions)).

## Installation

Requires Python 3.11 or newer. Install with [pipx](https://pipx.pypa.io/):

```bash
pipx install pdf-to-markdown-cli
```

You can also use `uv tool install pdf-to-markdown-cli` or `pip install pdf-to-markdown-cli`.

Documents are converted through the selected service's API. For the default backend, get a [Datalab API key](https://www.datalab.to/app/keys) and set it in your shell:

```bash
export DATALAB_API_KEY="your_api_key"
```

For Mistral, OpenAI or OpenRouter, use the corresponding key listed under [Backends](#backends).

## Usage

Convert a file:

```bash
pdf-to-md report.pdf
```

This writes `report.md` next to the input, with extracted images in `report_images/` if there are any. Input files are never overwritten. If two inputs share a name, such as `report.pdf` and `report.docx`, their outputs are `report.pdf.md` and `report.docx.md`.

To convert a folder and write the results elsewhere:

```bash
pdf-to-md papers/ -o papers-md/
```

The tool searches subfolders and preserves their structure under the output directory. It skips hidden files and folders. Existing outputs are also skipped; add `--overwrite` to replace them.

Preview the files, page counts and estimated cost before converting:

```bash
pdf-to-md papers/ --dry-run
```

A dry run makes no API calls and needs no key.

### Pages and output formats

```bash
# Convert the first ten pages and page 42
pdf-to-md book.pdf --page-range 0-9,42

# Include page boundaries in the output
pdf-to-md book.pdf --paginate

# Write HTML or JSON with Datalab
pdf-to-md slides.pptx --html
pdf-to-md form.pdf --json
```

Page ranges and output separators count PDF pages from 0. They do not follow a book's printed page numbers. A scan of two facing book pages counts as one PDF page.

### Images and text formatting

For text without extracted images or image descriptions:

```bash
pdf-to-md manual.pdf --no-images --no-image-captions
```

Markdown output joins hard-wrapped paragraph lines and writes superscripts as `<sup>…</sup>`. Use `--keep-line-breaks` or `--keep-superscripts` to preserve the backend's formatting. When included, image descriptions appear in the image alt text.

### Interrupted or failed conversions

Temporary API failures are retried automatically. If a file still fails, the batch continues with other files. Authentication or account errors stop the run.

After an interruption, run the same command again. Unfinished documents start again from the beginning.

By default, a failed conversion produces no document. Add `--keep-partial` to save successfully converted pages with comments marking failures. This works with Markdown and HTML. To retry a partial output, use `--overwrite`; otherwise it will be skipped too.

## Backends

Choose a service with `--backend` and set its API key. The links in the table open each service's key settings.

| Backend | API key | Output formats | Figures |
| --- | --- | --- | --- |
| `datalab` (default) | [`DATALAB_API_KEY`](https://www.datalab.to/app/keys) | Markdown, HTML, JSON | Extracted image files |
| `mistral` | [`MISTRAL_API_KEY`](https://console.mistral.ai/api-keys) | Markdown | Extracted image files |
| `openai` | [`OPENAI_API_KEY`](https://platform.openai.com/api-keys) | Markdown, HTML | Text descriptions |
| `openrouter` | [`OPENROUTER_API_KEY`](https://openrouter.ai/settings/keys) | Markdown, HTML | Text descriptions |

For example:

```bash
export MISTRAL_API_KEY="your_api_key"
pdf-to-md scan.pdf --backend mistral
```

`--api-key` overrides the environment variable. Datalab also accepts the older `MARKER_PDF_KEY` variable when `DATALAB_API_KEY` is unset.

### Datalab

The default `fast` mode suits digital PDFs and clear scans. Use `--mode balanced` for mixed layouts or `--mode accurate` for poor scans, dense tables and handwriting:

```bash
pdf-to-md scan.pdf --mode accurate
```

### Mistral OCR

The default model is `mistral-ocr-latest`. Use `--model mistral-ocr-4-1` to pin OCR 4.1. Mistral has no `--mode` setting.

With OCR 4.1, running headers, footers and page numbers are removed, while footnotes stay at the end of their page. Math uses `\( … \)` and `\[ … \]` delimiters. OCR 3 (`--model mistral-ocr-2512`) costs less but was less accurate on tables and Chinese in our tests.

### GPT-Luna

The `openai` and `openrouter` backends both use GPT-6 Luna by default. Start with `balanced` mode; `accurate` uses more reasoning but did not improve results in our scanned-book test. To select another model, pass `--model`, for example `--model gpt-5.6-luna`. The same model name works on both backends.

GPT-Luna can omit text or correct a printed misprint. Check transcriptions against the source when exact wording matters. The [model comparison](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/docs/ocr-models.md) has test results for all backends, including faded tables and historical spelling.

### Scans of facing pages

With Mistral or GPT-Luna, add `--split-spreads` when each scan shows two facing book pages:

```bash
pdf-to-md scanned-book.pdf --backend openai --split-spreads
```

This improves reading order and footnote placement while keeping the source PDF's page numbering. Mistral bills each half as a page. Do not use it for wide tables or slides: they would be cut in half.

## Supported inputs

Datalab accepts these formats:

| Type | Extensions |
| --- | --- |
| PDF | `.pdf` |
| Word processing | `.doc` `.docx` `.odt` |
| Presentations | `.ppt` `.pptx` `.odp` |
| Spreadsheets | `.xls` `.xlsx` `.xlsm` `.xltx` `.ods` `.csv` |
| Web and ebooks | `.html` `.htm` `.epub` |
| Images | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.tiff` `.tif` |

Mistral accepts `.pdf`, `.doc`, `.docx`, `.odt`, `.ppt`, `.pptx`, `.xlsx` and `.csv`, plus all image formats above and `.bmp`, `.avif` and `.heic`. Its page-range options also work for Office files.

OpenAI and OpenRouter accept `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp` and `.gif`.

Folder conversions include only formats the selected backend supports. Upload limits are 200 MB for Datalab and 50 MB for the other backends. PDFs are split by default; other documents must fit within the upload limit. Mistral also limits each request to 1,000 pages.

## Cost and speed

Each conversion reports its page count and cost, followed by a total for the run. `--dry-run` estimates PDF costs using the rates built into the tool:

| Backend and setting | Estimate per 1,000 PDF pages |
| --- | --- |
| Datalab `fast` or `balanced` | $4 |
| Datalab `accurate` | $10 |
| Mistral OCR 4.1 | $4 |
| GPT-6 Luna | About $0.80, depending on token use |

Actual charges depend on the service, plan and document. Dense tables can cost more with GPT-Luna. See current pricing from [Datalab](https://www.datalab.to/pricing), [Mistral](https://mistral.ai/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing) or [OpenRouter](https://openrouter.ai/openai/gpt-6-luna). OpenAI's `--api-option service_tier=flex` trades slower responses for a lower price.

The default is five concurrent requests. Adjust `-j` to match your service's limits. In a September 2026 Datalab run, three scanned books in English, Russian and German Fraktur totalled 1,563 pages and took 4 minutes 37 seconds, at a cost of $4.69.

## Command reference

```text
pdf-to-md INPUT [INPUT ...] [options]
```

Inputs can be any mix of files and directories. `python -m docs_to_md` runs the same CLI.

### Output

| Option | Description |
| --- | --- |
| `-f`, `--format FMT` | `markdown` (default), `html` or `json`, if supported by the backend. |
| `--html`, `--json` | Shortcuts for `--format html` and `--format json`. |
| `-o`, `--output-dir DIR` | Write results here, with the input folder structure. |
| `--overwrite` | Replace existing outputs. |
| `--keep-line-breaks` | Keep hard-wrapped paragraph lines in Markdown. |
| `--keep-superscripts` | Keep the backend's superscript formatting. |
| `--keep-partial` | Save pages that succeeded when a file partly fails. Markdown and HTML only. |

### Conversion

| Option | Description |
| --- | --- |
| `--backend NAME` | `datalab` (default), `mistral`, `openai` or `openrouter`. |
| `-m`, `--mode MODE` | `fast`, `balanced` or `accurate`. Datalab defaults to `fast`; GPT-Luna to `balanced`. Not available for Mistral. |
| `--model NAME` | Choose a model for Mistral, OpenAI or OpenRouter. |
| `--paginate` | Include page separators. |
| `--split-spreads` | Read facing book pages separately. Mistral and GPT-Luna only. |
| `--no-images` | Skip image extraction. |
| `--no-image-captions` | Skip image descriptions. |
| `--skip-cache` | Ignore cached Datalab results. |
| `--api-option KEY=VALUE` | Pass a field to the selected service's API. Repeatable. |

For `--api-option`, Datalab uses [Convert API form fields](https://documentation.datalab.to/api-reference/convert-document); Mistral uses [OCR API fields](https://docs.mistral.ai/api/endpoint/ocr); OpenAI and OpenRouter use Responses API fields. JSON values are decoded for Mistral and GPT-Luna. Examples:

```bash
pdf-to-md report.pdf --api-option extras=extract_links
pdf-to-md report.pdf --backend mistral --api-option table_format=html
pdf-to-md report.pdf --backend openai --api-option max_output_tokens=32000
```

### Pages and requests

| Option | Description |
| --- | --- |
| `--page-range RANGE` | Pages to convert, numbered from 0, for example `0,5-10`. |
| `--max-pages N` | Convert at most `N` pages of each document. |
| `--chunk-size N` | PDF pages per request. Default: `25` for Datalab and Mistral, `1` for GPT-Luna. |
| `--no-chunk` | Send each PDF's selected pages in one request. |
| `-j`, `--concurrency N` | Maximum concurrent requests. Default: `5`. |
| `--timeout SECONDS` | Timeout per request. Default: `3600`. |

### Run control

| Option | Description |
| --- | --- |
| `--api-key KEY` | Override the backend's API key. |
| `-n`, `--dry-run` | Preview files, page counts, chunk counts and estimated cost. |
| `-q`, `--quiet` | Show only errors and converted paths. |
| `-v`, `--verbose` | Print debug logs. |
| `-h`, `--help` | Show command help. |
| `--version` | Print the version and exit. |

## Scripting

Successful output paths go to stdout, one per line. Progress and errors go to stderr. Partial outputs from `--keep-partial` count as failures and are omitted from stdout.

```bash
pdf-to-md papers/ -q > converted-files.txt
```

| Exit status | Meaning |
| --- | --- |
| `0` | All inputs were converted or skipped. |
| `1` | At least one file failed. |
| `2` | Usage, configuration or account error. |
| `130` | Interrupted with Ctrl-C. |

Set `NO_COLOR=1` to disable colored terminal output.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `No API key found` | Set the environment variable for the selected [backend](#backends). |
| `Authentication failed` | Check the key in that service's dashboard. |
| `Payment required` or `out of credits` | Check the account's balance and spending limit. |
| `exists (use --overwrite)` | Add `--overwrite` if you want to replace the output. |
| `timed out` | Raise `--timeout` or lower `--chunk-size`. |
| `returned N pages for M` | Lower `--chunk-size`; for GPT-Luna, use `1`. |
| Frequent throttling | Lower `-j` to stay within your plan's limits. |

For other failures, rerun with `-v` and [open an issue](https://github.com/SokolskyNikita/pdf-to-markdown-cli/issues) with the error output.

## Sample conversions

The [examples directory](https://github.com/SokolskyNikita/pdf-to-markdown-cli/tree/main/examples) pairs source PDFs with output from the default Datalab backend. A few examples:

| Output | Content |
| --- | --- |
| [Algebraic geometry notes](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/equations.md) | Mathematics rendered as LaTeX |
| [1880 census tables](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/census_1880_tables_en.md) | Faded microfiche, side-by-side tables |
| [Grimm's Fairy Tales](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/grimm_fairy_tales_de.md) | German Fraktur |
| [Shijing Gupu](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/shijing_gupu_zh.md) | Vertical Chinese text and music notation |
| [Lane's Arabic-English Lexicon](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/lane_arabic_english_lexicon_ar.md) | Three columns with vocalized Arabic |
| [Newton's Principia](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/newton_principia_la.md) | Seventeenth-century Latin and diagrams |

The [full sample list](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/README.md) includes sources and more languages.

## Upgrading from 0.x

Version 1.0 changed output names and failure reporting. Old flags remain accepted: `--llm` means `--mode balanced` and `--max` means `--mode accurate`; `--strip`, `--force` and `--langs` are ignored with a warning. The aliases `--pages`, `--noimg`, `-cs` and `-mp` still work. The old `~/.docs_to_md/` directory is no longer used and can be deleted.

See the [changelog](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/CHANGELOG.md) for the full migration notes and release history.

## Development

[CONTRIBUTING.md](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/CONTRIBUTING.md) covers setup, tests and releases. [HOW-IT-WORKS.md](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/HOW-IT-WORKS.md) describes the conversion pipeline and backend internals.

## Acknowledgements

Conversion is provided by [Datalab](https://www.datalab.to/) and its [Marker](https://github.com/datalab-to/marker) engine, Mistral OCR or OpenAI's GPT-Luna. This project is not affiliated with those providers or OpenRouter.

## License

[MIT](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/LICENSE) © Nikita Sokolsky
