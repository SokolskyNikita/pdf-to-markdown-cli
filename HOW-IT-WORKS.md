# How pdf-to-md works

This document covers the conversion pipeline, backend behavior, and the reasons behind implementation choices. For installation, commands, formats, and costs, see the [README](README.md). For development setup and the module map, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Conversion pipeline

1. **Plan.** Discover inputs the chosen backend accepts and assign deterministic output paths. Skip inputs whose output file or images folder already exists, unless `--overwrite` is set.
2. **Split.** Select PDF pages locally and cut them into chunks of `--chunk-size` pages: 25 by default for Datalab and Mistral, 1 for GPT-Luna. Other formats are uploaded whole.
3. **Convert.** Process up to `--concurrency` chunks at once (default 5). Each backend turns a chunk into text, images, page metadata, and cost information.
4. **Merge.** Join chunk results in source-page order, renumber page references, and rename images to avoid collisions.
5. **Write.** Write the document to a temporary file and rename it into place. A failed chunk normally prevents that document from being written; `--keep-partial` allows successful pages to be saved.

The pipeline in [`pipeline.py`](src/docs_to_md/pipeline.py) is backend-agnostic. Backends implement the [`Backend`](src/docs_to_md/backends/base.py) contract and return `ChunkOutput` objects using the page and image conventions understood by the assembler.

## Input discovery and output names

[`discovery.py`](src/docs_to_md/discovery.py) walks directories recursively, ignoring hidden files and directories and recognizable generated image folders. It also skips recognizable outputs from earlier conversions, so directory runs don't convert those results again. This includes the current `<stem>_images/` layout and the legacy `images_<key>/` layout.

An input normally becomes `<stem><output-extension>`, with images in `<stem>_images/`. The `-o` directory mirrors the structure under each directory input. Names are compared case-insensitively:

- Same-stem inputs such as `a.pdf` and `a.docx` retain their source extensions: `a.pdf.md` and `a.docx.md`.
- Remaining collisions get `_2`, `_3`, and subsequent suffixes.
- An input whose output would be itself gets a `_converted` suffix.
- No planned output may overwrite an input.

Generated names such as `<name.ext><output-extension>` and `<stem>_converted<output-extension>` are recognizable on their own. A plain `<stem><output-extension>` is treated as generated only when its corresponding `<stem>_images/` directory exists.

## Page selection and chunking

[`pdf.py`](src/docs_to_md/pdf.py) applies `--page-range` and `--max-pages` before uploading a PDF, so only selected pages are sent for conversion. Each chunk records its 0-based source-page indexes for later assembly. `--no-chunk` puts all selected pages in one request. If the entire PDF fits in a single chunk and all pages are selected, the original file can be used without rewriting it.

Non-PDF documents are sent whole, subject to the backend's upload limit. Their page selection is passed to the backend API instead of being applied locally.

Chunks run on a shared thread pool. Datalab uploads a chunk and polls for its result; Mistral and GPT-Luna answer in a single synchronous request. The HTTP clients retry transient failures with capped backoff and honor `Retry-After`. Datalab also resubmits results that report a page-rate limit. The OpenAI client, also used by Mistral, does not retry read timeouts.

## Backend behavior

### Datalab

The default backend uses Datalab's hosted version of the open-source [Marker](https://github.com/datalab-to/marker) engine. [`backends/datalab/`](src/docs_to_md/backends/datalab/) maps configuration to Convert API form fields, submits each document, and polls until completion or timeout. Results may arrive inline or through a separate `result_url`.

Markdown, HTML, JSON, images, metadata, and cost information come from the API response. JSON output is Marker's block tree, including page and position data. Version 1.0 moved from the legacy API to `/api/v1/convert`.

### Mistral OCR

[`backends/mistral/`](src/docs_to_md/backends/mistral/) sends each chunk to `/v1/ocr`. Documents use `document_url` and images use `image_url`, both containing base64 data URLs. Results contain per-page Markdown, image data, and page indexes. Table placeholders are replaced with their returned contents; image placeholders are linked to extracted files or removed when images are disabled.

Header and footer extraction is enabled for the default model. OCR 4.1 puts footnotes in the footer and, on two-page scans, sometimes in the header. The parser adds these notes back at the end of the page while dropping page numbers and repeated running footers. OCR 3 keeps headers and footers in the text because extracting them can misplace body text, including an entire Chinese sample page in our tests.

In October 2026 tests, OCR 4.1 found every sample's required words and read 14 of the 15 checked cells in the dense 1980 census table. It converted the 25 sample pages in 11 seconds for 10¢. On the faded 1880 census microfiche, it got 7 of 16 checked cells wrong; GPT-Luna and Datalab's `accurate` mode got all 16 right. These observations inform the README's quality guidance; the broader comparison lives in [`docs/ocr-models.md`](docs/ocr-models.md).

### GPT-Luna through OpenAI or OpenRouter

[`backends/openai/`](src/docs_to_md/backends/openai/) calls the Responses API. PDFs are sent as `input_file` at high detail and images as `input_image`. The model sees a PDF page's image and text layer. A strict JSON response schema asks for one transcription string per page; the backend then joins those strings using the same page conventions as other backends.

`--mode` maps to reasoning effort: `fast` is `none`, `balanced` is `low`, and `accurate` is `medium`. OpenRouter uses the same request structure, adds the `openai/` model prefix when no provider is specified, and pins its `file-parser` plugin to the `native` engine so the model receives the PDF itself.

The default chunk size is one page. In tests on scans of facing book pages, multi-page requests sometimes returned the expected number of strings but shifted text between pages. Single-page requests were also faster and cost no more. Page-count recovery works as follows:

- A single-page request returning several page strings is joined back into one source page, accommodating the halves of a scanned spread.
- A larger chunk returning the wrong count is retried once, then split and transcribed one page at a time if the count is still wrong.

The [prompt](src/docs_to_md/backends/openai/prompt.py) asks for printed spelling, misprints, and editorial marks such as `[sic]` to be preserved. The model still sometimes corrects misprints or drops a heading label or LaTeX backslash. In our sample tests, `balanced` passed every check, including the 1880 microfiche table. In the scanned-book benchmark, `accurate` scored no better than `fast` and cost twice as much as `balanced`. Datalab `accurate` was the strongest overall, but no backend preserved every printed spelling. See the [scanned-book results](docs/ocr-models.md#scanned-book-test) for evidence and limitations.

## Splitting facing-page scans

With `--split-spreads`, [`spreads.py`](src/docs_to_md/spreads.py) cuts unrotated PDF pages wider than 1.2 times their height into left and right halves. Other pages stay whole. The split copies lose their invisible OCR text layer: merely cropping a PDF leaves the whole spread's text available, which OpenAI would otherwise read with each half. Visible text is kept, and the source file is unchanged.

GPT-Luna transcribes each half in its own request. Mistral receives the halves together in one request and bills each half as a page. Both backends join the half-page transcriptions back into one result per source PDF page, preserving the original page numbering.

Without splitting, GPT-Luna tends to move the left page's footnotes to the end of the scan and sometimes transcribes only one half. Splitting raised its `balanced` score from 94.8% to 98.8% at the same measured cost in our scanned-book test. This is why the README recommends the flag for facing-page scans; it also cuts genuinely wide pages such as tables and slides.

## Assembly and Markdown cleanup

[`assemble.py`](src/docs_to_md/assemble.py) merges results in source-page order. It renumbers Markdown `{N}----` separators, `page-N-M` anchors and links, HTML `data-page-id` attributes, and JSON `/page/N/` ids, content references, and `page` fields. The numbers identify original PDF pages from 0, including when only a page range was selected.

Images from different chunks receive unique names, and links are rewritten and URL-encoded to point to the final images directory.

[`markdown.py`](src/docs_to_md/markdown.py) normalizes Markdown output:

- Hard-wrapped paragraph lines are joined while structural line breaks are preserved. `--keep-line-breaks` disables this.
- Paragraphs that duplicate an image's alt text are removed; the description remains in the alt text.
- LaTeX-only superscripts such as `$^{a}$`, Unicode superscript digits such as `¹`, and modifier letters such as `Ex.ᵐᵒ` become `<sup>…</sup>` outside code fences. The ordinal characters `ª` and `º` stay unchanged. `--keep-superscripts` disables this normalization.

## Failures, writes, and run state

A failed chunk normally cancels its sibling chunks and leaves the document unwritten, while other files continue. Authentication, account, and other fatal API errors stop the whole run. Cancellation checks and interruptible retry sleeps let workers respond to a shared stop signal.

With `--keep-partial`, sibling chunks continue. Each missing PDF page gets a placeholder; in Markdown it is `<!-- pdf-to-md: page N failed: … -->`. A partly converted file still counts as failed, produces exit status 1, and is omitted from stdout so downstream tools receive only successfully converted paths. If every chunk fails, no document is written. An existing partial output is skipped on the next run unless `--overwrite` is set.

The output document is written with LF line endings to a temporary file and atomically renamed into place. Extracted images go into the document's images directory, replacing old images when overwriting.

There is no persistent run state or checkpoint database. Temporary chunks live in a system `tempfile.TemporaryDirectory`. Re-running skips existing outputs and starts unfinished documents again; it does not resume an unfinished document from its last completed chunk.
