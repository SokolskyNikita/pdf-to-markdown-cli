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

`pdf-to-md` is a command-line tool that converts documents to Markdown, HTML, or JSON with the [Datalab](https://www.datalab.to/) Convert API, the hosted version of the open-source [Marker](https://github.com/datalab-to/marker) engine. It can also read PDFs, Office files, and images with [Mistral OCR](#ocr-with-mistral), or transcribe PDFs and images with OpenAI's GPT-Luna, called [directly or through OpenRouter](#transcribing-with-gpt-luna). It handles the tedious parts for you: splitting big PDFs, uploading in parallel, retrying, stitching the results back together, and fixing page numbers and image links.

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

Requires Python 3.11 or newer. [pipx](https://pipx.pypa.io/) installs it in its own isolated environment:

```bash
pipx install pdf-to-markdown-cli
```

`uv tool install pdf-to-markdown-cli` and `pip install pdf-to-markdown-cli` work too.

Then get an API key from [datalab.to/app/keys](https://www.datalab.to/app/keys) and export it:

```bash
export DATALAB_API_KEY="your_api_key"
```

To use Mistral OCR instead, export `MISTRAL_API_KEY` and pass `--backend mistral`. For GPT-Luna, export `OPENAI_API_KEY` or `OPENROUTER_API_KEY` and pass `--backend openai` or `--backend openrouter`.

## Quick start

```bash
pdf-to-md report.pdf
```

This writes `report.md` next to the PDF, plus a `report_images/` folder if the document contains images. That's it.

## Recipes

```bash
# Mirror a folder tree elsewhere
pdf-to-md ~/papers -o ~/papers-md

# Preview files, pages, and list-price cost, at no cost
pdf-to-md ~/papers --dry-run

# Best quality for hard scans and tables
pdf-to-md scan.pdf --mode accurate

# First ten pages plus page 42 (0-based)
pdf-to-md book.pdf --page-range 0-9,42

# HTML or JSON instead of Markdown
pdf-to-md slides.pptx --html
pdf-to-md form.pdf --json

# Mark page boundaries in the output
pdf-to-md contract.pdf --paginate

# Text only: no images or descriptions
pdf-to-md manual.pdf --no-images \
  --no-image-captions

# OCR with Mistral OCR
pdf-to-md scan.pdf --backend mistral

# Transcribe with GPT-Luna
pdf-to-md scan.pdf --backend openai
pdf-to-md scan.pdf --backend openrouter

# Redo everything, replacing old outputs
pdf-to-md ~/papers --overwrite

# Feed converted files to other tools
pdf-to-md ~/papers -q | xargs wc -w
```

## How it works

1. **Plan.** Inputs are discovered recursively. Hidden files and folders this tool generated earlier are ignored. Each input gets a deterministic output path, and inputs whose output already exists are skipped.
2. **Split.** PDFs are cut into chunks of `--chunk-size` pages (default 25 for Datalab and Mistral, 1 for GPT-Luna). Page selection with `--page-range` or `--max-pages` happens here, so only those pages are uploaded and billed. Other formats are uploaded whole.
3. **Convert.** Up to `--concurrency` chunks (default 5) are processed at once. Each one is uploaded, then polled until it's done (Datalab) or answered in one request (Mistral, GPT-Luna). Throttling and server errors are retried, honoring the API's `Retry-After`.
4. **Merge.** Chunk results are joined in page order. Page separators, HTML page ids, JSON block ids, and in-document anchors are renumbered to match the original document. Images are renamed so they never collide, and links to them are URL-encoded.
5. **Write.** The output is written to a temporary file and renamed into place, so an interrupted run never leaves a partial file behind. If any chunk fails, the file isn't written, unless you pass `--keep-partial`.

## Output

```text
papers/
├── report.pdf
├── report.md       ← the document
└── report_images/  ← images, if any
```

- If two inputs would produce the same name (`a.pdf` and `a.docx`), both keep their source extension: `a.pdf.md` and `a.docx.md`. Names are compared case-insensitively, and an output never overwrites an input.
- Hard-wrapped paragraph lines are joined in Markdown output (disable with `--keep-line-breaks`). Image descriptions live in the image alt text.
- Superscripts are written as `<sup>…</sup>` in Markdown, whichever backend produced them: Mistral's `$^{a}$` and Unicode such as `Ex.ᵐᵒ` or `¹` are converted. The ordinals `ª` and `º` are left alone. `--keep-superscripts` turns this off.
- `--paginate` separators number the PDF's pages from 0 (`{0}------…`), as `--page-range` does. They don't follow the page numbers printed in a book, and a scan showing two facing pages is one page.
- With `--keep-partial`, a file whose chunks partly fail is still written, with `<!-- pdf-to-md: page N failed: … -->` in place of each missing page. The run still exits with status 1, and the path isn't printed to stdout. Re-run with `--overwrite` to fill the gaps.

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

These are Datalab's formats. [Mistral](#ocr-with-mistral) and [GPT-Luna](#transcribing-with-gpt-luna) accept fewer, and the tool only picks up files the chosen backend can read.

## Quality, speed, and cost

`--mode` picks a Datalab processing mode:

| Mode | Use it for |
| --- | --- |
| `fast` (API default) | Clean digital PDFs and good scans. |
| `balanced` | Mixed documents with tables, forms, or harder layouts. |
| `accurate` | The hardest material: poor scans, dense tables, handwriting. |

Every result line shows what Datalab billed, and the run summary adds it up. In our September 2026 test runs, conversions cost about 0.3¢ per page ($3 per 1,000 pages). See [Datalab's pricing](https://www.datalab.to/pricing) for current rates. `--dry-run` estimates each file's cost at list price ($4 per 1,000 pages for `fast` and `balanced`, $10 for `accurate`) before you spend anything.

Datalab and Mistral bill per PDF page, so a scan that shows two facing book pages costs one page.

Throughput depends on your plan's limits. With the default of 5 concurrent requests (the free tier's limit), the 1,563-page run above took 4 minutes 37 seconds. Paid plans allow far more concurrency, so raise `-j` to match yours.

## OCR with Mistral

`--backend mistral` sends each chunk to [Mistral OCR](https://docs.mistral.ai/capabilities/document_ai/basic_ocr) through Mistral's own API. It returns Markdown for every page and crops out figures as image files, as Datalab does. Running headers, footers, and page numbers are left out of the text. Mistral returns footnotes along with the footer, so they are added back at the end of their page.

| | Datalab (default) | Mistral OCR |
| --- | --- | --- |
| Inputs | PDFs, Office, ebooks, images | PDFs, Word, PowerPoint, Excel, ODT, CSV, images |
| Outputs | Markdown, HTML, JSON | Markdown |
| Figures | Extracted as image files | Extracted as image files |
| Pages per request | 25 | 25 |
| `--mode` | Datalab processing mode | Not available |
| Price per 1,000 pages | See [pricing](https://www.datalab.to/pricing) | $4 ([pricing](https://mistral.ai/pricing)) |

Mistral accepts `.pdf`, `.doc`, `.docx`, `.odt`, `.ppt`, `.pptx`, `.xlsx`, `.csv`, and `.png` `.jpg` `.jpeg` `.webp` `.gif` `.tif` `.tiff` `.bmp` `.avif` `.heic` images, up to 50 MB and 1,000 pages per request. `--page-range` and `--max-pages` work for Office files too.

The default model is `mistral-ocr-4-0` (OCR 4.0). In September 2026 tests it found every sample's required words and read the dense 1980 census table cell for cell. It converted all 25 sample pages in 13 seconds for 10¢. OCR 4.1 (`--model mistral-ocr-latest`) did no better on our samples and writes math as `\( \)` instead of `$`. OCR 3 (`--model mistral-ocr-2512`) costs half as much but read the tables and the Chinese sample much worse. Mistral's weak spot is faded scans full of numbers: on the 1880 census microfiche it misread 6 of the 16 hard cells we checked, all of which GPT-Luna and Datalab's `accurate` mode got right.

For scans of two facing book pages, `--split-spreads` sends each half as a page of its own, which puts each page's footnotes in the right place (see [GPT-Luna](#transcribing-with-gpt-luna) below). Mistral bills each half as a page.

`--api-option KEY=VALUE` adds any other [OCR API](https://docs.mistral.ai/api/endpoint/ocr) field, with JSON values decoded. For example, `--api-option table_format=html` writes tables as HTML inside the Markdown, and `--api-option extract_header=false` keeps running headers in the text.

## Transcribing with GPT-Luna

`--backend openai` sends each chunk to OpenAI's [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), a low-cost vision model, through the Responses API. `--backend openrouter` sends the same request to the same model through [OpenRouter](https://openrouter.ai/openai/gpt-6-luna). The model sees each page's image and its text layer and writes one transcription per page. The tool checks that it got exactly one page back for every page sent, then merges the pages the same way as Datalab results.

| | Datalab (default) | GPT-Luna |
| --- | --- | --- |
| Inputs | PDFs, Office, ebooks, images | PDFs and images |
| Outputs | Markdown, HTML, JSON | Markdown, HTML |
| Figures | Extracted as image files | Described in text |
| Pages per request | 25 | 1 |
| `--mode` | Datalab processing mode | Reasoning effort |

Datalab remains the default. Mistral and GPT-Luna run only when you choose them with `--backend`.

In September 2026 test runs, GPT-Luna transcribed all 25 sample pages for about 2¢ on either route. That's 0.08¢ per page on average and about 0.2¢ for the dense census tables, versus about 0.3¢ per page on Datalab. Both routes bill the same token rates, and results show the cost of each file. `--dry-run` estimates about 0.08¢ per page, assuming typical token use; dense tables cost more. For half price in exchange for slower responses, add `--api-option service_tier=flex` (OpenAI only).

`--mode` maps to reasoning effort: `fast` is none, `balanced` (the default) is low, and `accurate` is medium. In `balanced` mode every sample passed its checks, including the 1880 microfiche table that needs Datalab's `accurate` mode. On our scanned-book test, `accurate` scored no better than `fast` and cost twice as much as `balanced`. As with any language model, output can vary between runs: in repeated tests it occasionally dropped a heading label or a LaTeX backslash.

`--model` picks another model, such as `gpt-5.6-luna`. OpenRouter adds the `openai/` prefix when the name has none, so the same flag works on both routes. `--api-option KEY=VALUE` adds any other Responses API field, with JSON values decoded, e.g. `--api-option max_output_tokens=32000`.

Each page is sent as its own request by default. On scans that show two facing book pages, multi-page requests sometimes came back with the right number of pages but text shifted between them. One page per request was also faster and cost no more. If you raise `--chunk-size` and a chunk comes back with the wrong page count, it's retried once, then sent again one page at a time. A single page that comes back as two (the two halves of a spread) is joined.

For scans that show two facing book pages, add `--split-spreads`: every landscape PDF page is sent as its left and right halves, one request each, and the two transcriptions are joined back into one page. Without it, GPT-Luna tends to move the left page's footnotes to the end of the scan and occasionally transcribes only one of the two pages. In our scanned-book test it raised `balanced` from 94.8% to 98.8% at the same cost. Split pages lose any invisible OCR text layer, because the model would otherwise read the whole spread's text with each half. Don't use the flag for documents with genuinely landscape pages, such as wide tables or slides, which would be cut in half.

The prompt asks the model to keep printed spelling, misprints, and editorial marks such as `[sic]` exactly. In practice GPT-Luna still "corrects" some misprints. No backend keeps every printed spelling; Datalab `accurate` was the most accurate overall in [our scanned-book test](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/docs/ocr-models.md#scanned-book-test).

## Sample conversions

[`examples/`](https://github.com/SokolskyNikita/pdf-to-markdown-cli/tree/main/examples) holds sample documents next to their actual output from this tool:

| Sample (links to output) | Language | What it tests |
| --- | --- | --- |
| [Alice in Wonderland](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/alice_in_wonderland_sample.md) | English | Illustrated novel, curly quotes |
| [Algebraic geometry notes](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/equations.md) | English | Mathematics rendered as LaTeX |
| [*Origin of Species* (1859)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/darwin_origin_of_species_en.md) | English | Old scan, fold-out tree diagram |
| [*War and Peace* (1937 ed.)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/tolstoy_war_and_peace_ru.md) | Russian | Cyrillic mixed with French, footnotes |
| [*Grimm's Fairy Tales* (1857)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/grimm_fairy_tales_de.md) | German | Fraktur blackletter typeface |
| [*Shijing Gupu* (1908)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/shijing_gupu_zh.md) | Chinese | Vertical text, music notation |
| [1880 Census tables](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/census_1880_tables_en.md) | English | Microfiche scan, side-by-side tables |
| [1980 Census ancestry](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/census_1980_ancestry_en.md) | English | Dense table, two-level headers |
| [Lane's *Arabic-English Lexicon* (1863)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/lane_arabic_english_lexicon_ar.md) | Arabic, English | Three columns, vocalized Arabic inline |
| [Gesenius' *Hebrew Grammar* (1898)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/gesenius_hebrew_grammar_he.md) | Hebrew, English | Pointed Hebrew paradigms, margin letters |
| [Loeb *Odyssey* (1919)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/homer_odyssey_loeb_grc.md) | Greek, English | Polytonic Greek, critical apparatus |
| [*Bhagavad-Gita* (1922)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/besant_bhagavad_gita_sa.md) | Sanskrit, English | Devanagari on a cropped scan |
| [Newton's *Principia* (1687)](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/newton_principia_la.md) | Latin | Long s, ligatures, inline diagram |

See [examples/README.md](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/examples/README.md) for sources and how the samples are used in tests.

## Command reference

```text
pdf-to-md INPUT [INPUT ...] [options]
```

`INPUT` is any mix of files and directories. The tool also runs as `python -m docs_to_md`.

**Output**

| Option | Description |
| --- | --- |
| `-f`, `--format FMT` | `markdown` (default), `html`, or `json`. `--html` and `--json` are shortcuts. |
| `-o`, `--output-dir DIR` | Write here instead of next to each input. Folder structure under directory inputs is mirrored. |
| `--overwrite` | Replace existing outputs instead of skipping those inputs. |
| `--keep-line-breaks` | Keep hard-wrapped paragraph lines in Markdown. |
| `--keep-superscripts` | Keep superscripts as the backend wrote them instead of `<sup>`. |
| `--keep-partial` | If some pages of a file fail, write the rest with a comment in place of each failed page. |

**Conversion**

| Option | Description |
| --- | --- |
| `--backend NAME` | `datalab` (default), `mistral`, `openai`, or `openrouter`. |
| `-m`, `--mode MODE` | `fast`, `balanced`, or `accurate`. Defaults to `fast` on Datalab and `balanced` on GPT-Luna. Mistral has no modes. |
| `--model NAME` | Mistral and GPT-Luna only. Defaults: `mistral-ocr-4-0` and `gpt-6-luna`. |
| `--paginate` | Insert page separators, numbered from 0 by PDF page. |
| `--split-spreads` | Mistral and GPT-Luna. Send each half of a landscape PDF page (a scan of two facing pages) as its own page, then join them. Mistral bills each half as a page. |
| `--no-images` | Don't extract images. |
| `--no-image-captions` | Don't generate image descriptions. |
| `--skip-cache` | Ignore Datalab's server-side cache of previous results. |
| `--api-option KEY=VALUE` | Send any other API field: a [Convert API](https://documentation.datalab.to/api-reference/convert-document) form field, an OCR API field for Mistral, or a Responses API field for GPT-Luna. Repeatable, e.g. `--api-option extras=extract_links`. |

**Pages and chunking**

| Option | Description |
| --- | --- |
| `--page-range RANGE` | 0-based pages to convert, e.g. `0,5-10`. |
| `--max-pages N` | Convert at most `N` pages of each document. |
| `--chunk-size N` | PDF pages per request. Default: `25` on Datalab and Mistral, `1` on GPT-Luna. Smaller chunks mean more parallelism but more requests. |
| `--no-chunk` | Send each PDF as one request. |

**Run control**

| Option | Description |
| --- | --- |
| `--api-key KEY` | API key. Prefer the environment variable, which keeps the key out of shell history. |
| `-j`, `--concurrency N` | Requests in flight at once. Default: `5`. |
| `--timeout SECONDS` | Give up on a single request after this long. Default: `3600`. |
| `-n`, `--dry-run` | Show what would be converted, with page and chunk counts and a list-price cost estimate. Makes no API calls and needs no key. |
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
| `DATALAB_API_KEY` | API key, the same variable Datalab's SDK uses. The pre-1.0 name `MARKER_PDF_KEY` also works. |
| `MISTRAL_API_KEY` | Mistral API key, for `--backend mistral`. |
| `OPENAI_API_KEY` | OpenAI API key, for `--backend openai`. |
| `OPENROUTER_API_KEY` | OpenRouter API key, for `--backend openrouter`. |
| `NO_COLOR` | Disable colored output. |

`--api-key` overrides whichever variable the chosen backend reads. The tool keeps no state between runs. Temporary chunk files live in the system temp directory and are deleted when the run ends.

## Troubleshooting

| Message | What to do |
| --- | --- |
| `No API key found` | Set the backend's key variable (see [Configuration](#configuration)). |
| `Authentication failed` | The key was rejected. Check it on the [Datalab](https://www.datalab.to/app/keys), [Mistral](https://console.mistral.ai/api-keys), [OpenAI](https://platform.openai.com/api-keys), or [OpenRouter](https://openrouter.ai/settings/keys) dashboard. |
| `Payment required` | Your Datalab account is out of credits. |
| `out of credits` | Your Mistral, OpenAI, or OpenRouter account needs credits or a higher spend limit. |
| `returned N pages for M` | GPT-Luna merged or split pages. Lower `--chunk-size`. |
| `exists (use --overwrite)` | The output is already there. Add `--overwrite` to redo it. |
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

Conversion quality comes from [Marker](https://github.com/datalab-to/marker) and the [Datalab](https://www.datalab.to/) API, from Mistral OCR, or from OpenAI's GPT-Luna. This is an independent project and isn't affiliated with Datalab, Mistral AI, OpenAI, or OpenRouter.

## License

[MIT](https://github.com/SokolskyNikita/pdf-to-markdown-cli/blob/main/LICENSE) © Nikita Sokolsky
