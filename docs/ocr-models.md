# OCR model comparison

This comparison covers the backends available in `pdf-to-md` and other remote and local models we considered. The research dates are 29–30 September 2026, with Mistral OCR 4.1 results added on 11 October. Prices and model versions below refer to those dates.

For installation and commands, see the [README](../README.md). Request handling and output cleanup are documented in [HOW-IT-WORKS.md](../HOW-IT-WORKS.md).

## Choosing a supported backend

| Backend | Use it for | Output | Figures | Cost per 1,000 pages |
| --- | --- | --- | --- | --- |
| Datalab | The widest format support; historical books with footnotes | Markdown, HTML, JSON | Image files | $4 for `fast` or `balanced`, $10 for `accurate` at list price |
| Mistral OCR 4.1 | Fast Markdown conversion with extracted images | Markdown | Image files | $4 at list price |
| GPT-6 Luna | Low-cost transcription, especially faded tables | Markdown, HTML | Text descriptions | About $0.80 measured with the PDF backend; about $2 for dense tables |

Datalab is the default. Select the others with `--backend mistral`, `--backend openai` or `--backend openrouter`. The last two use the same GPT-6 Luna model.

Datalab's `accurate` mode had the highest word accuracy in our scanned-book test. Its `fast` mode costs less and suits clear documents. The census tests below show why neither setting should be assumed to read every table correctly.

Mistral OCR 4.1 improved on OCR 3 in both table reading and Chinese text. Faded rows of numbers remained its weak spot. Use `--model mistral-ocr-4-1` to pin that version; the default `mistral-ocr-latest` alias can change without a tool update.

GPT-Luna costs less but does not extract image files. Its output can vary between runs, including occasional missing text and altered spelling. `balanced` is the default; more reasoning did not consistently improve our book results.

All prices are in US dollars. Measured costs depend on the documents and request format. Prices shown exclude provider batch discounts; `pdf-to-md` does not use batch APIs.

## Results on our documents

The exploratory comparison used eight PDFs totalling 16 pages from [examples](../examples/README.md). Later backend tests used the expanded 25-page set. These were small tests of particular documents, not estimates of accuracy across all document types.

### Tables and mixed documents

The original checks covered 17 required words and 31 census values checked against the scans. The census cells were chosen because Datalab and Mistral disagreed on them, so they concentrate on difficult cases.

| Model or output | Keywords, of 17 | 1880 census cells, of 16 | 1980 census cells, of 15 |
| --- | --- | --- | --- |
| Datalab committed outputs | 17 | 16 | 2 |
| Mistral OCR 4.1 | 17 | 9 | 14 |
| Mistral OCR 3 | 16 | 1 | 11 |
| GPT-6 Luna, exploratory image test | 16 | 16 | 15 |

The Datalab outputs used `accurate` for the faded 1880 scan and `fast` for the dense 1980 table. The checked cells do not cover the whole document: a later review found three other wrong digits in Datalab's 1880 output.

GPT-Luna's missing keyword was a case change from `COROLLARY` to `Corollary`. Later tests through the PDF backend passed all sample checks. These results came from different runs, so they should not be read as a guarantee of identical output.

Mistral OCR 4.1 also extracted nine figures where OCR 3 extracted four and took about half as long per page.

### Scanned-book test

The [scanned-book benchmark](../benchmarks/scanned_books/README.md) contains 16 PDF pages of Portuguese, Dutch and French letters. Eight are scans of facing pages. The references retain historical spelling and misprints.

The scores measure word accuracy, preservation of 42 spelling probes, recovery of 47 footnotes and eight checks of left-to-right reading order. Results are from 30 September 2026, except Mistral's results from 11 October. The table includes the original mode comparisons and selected runs with `--split-spreads`; the benchmark README has every saved result.

| Backend and setting | Word accuracy | Spelling, of 42 | Footnotes, of 47 | Order, of 8 | Measured cost for 16 PDF pages |
| --- | --- | --- | --- | --- | --- |
| Datalab `fast` | 98.81% | 18 | 47 | 7 | $0.048 |
| Datalab `balanced` | 99.14% | 16 | 47 | 8 | $0.048 |
| Datalab `accurate` | 99.50% | 21 | 47 | 8 | $0.120 |
| Mistral OCR 4.1 | 98.13% | 23 | 47 | 3 | $0.064 |
| Mistral OCR 4.1, split spreads | 98.86% | 24 | 47 | 8 | $0.096 |
| GPT-6 Luna `fast` | 98.38% | 26 | 47 | 3 | $0.013 |
| GPT-6 Luna `balanced` | 94.79% | 23 | 45 | 4 | $0.016 |
| GPT-6 Luna `accurate` | 98.42% | 22 | 43 | 6 | $0.026 |
| GPT-6 Luna `balanced`, split spreads | 98.78% | 26 | 47 | 8 | $0.016 |
| GPT-6 Luna `balanced` via OpenRouter, split spreads | 98.76% | 27 | 47 | 8 | $0.017 |

Use `--split-spreads` with Mistral or GPT-Luna for scans of facing book pages. Without it, GPT-Luna sometimes omitted one half of a scan, while both backends misplaced left-page footnotes. Splitting improved reading order in these tests. Mistral bills each half as a page, which raised the cost of this mixed set by 50%; GPT-Luna's measured cost stayed about the same.

No setting preserved all historical spellings. Even the best result kept only 27 of the 42 probes. Some outputs modernised words such as `pretenção`; others corrected printed misprints such as `benegnidade`. High word accuracy does not imply a faithful edition of the text.

## Other remote models and services

GPT-Luna is included as a reference for possible additions. The other models and services have not been validated as `pdf-to-md` backends.

### General vision models

This experiment sent each page as a 200-DPI image through OpenRouter, using the same Markdown prompt for every model. Costs are measured at standard rates. They differ from the supported PDF backend's costs because the inputs and request format differ.

"Chinese agreement" measures similarity to Datalab's committed Chinese output, not correctness against a reference transcription. All models below described figures rather than extracting image files.

| Model | Census cells, of 31 | Chinese agreement | Seconds per page | Measured cost per 1,000 pages | Observed problems |
| --- | --- | --- | --- | --- | --- |
| Gemini 3.8 Flash | 31 | 98.9% | ~11 | $5.97 | None in these checks |
| GPT-6 Luna | 31 | 89.4% | ~14 | $1.27 | Lower agreement on Chinese |
| Gemini 3.1 Pro | 31 | 97.0% | ~11 | $18.52 | None in these checks |
| Claude Sonnet 5.5 | 31 | 98.7% | ~9 | $21.33 | One page blocked by content filtering |
| Claude Opus 5.5 | 31 | 97.7% | ~13 | $41.15 | Two pages blocked by content filtering |
| GPT-5.4 | 29 | 89.9% | ~20 | $26.42 | Two digit errors |
| GPT-5.2 | 31 | 18.9% | ~20 | $27.12 | Refused a Chinese page |

Gemini 3.8 Flash is the first candidate to test further: it passed the checks without refusals and cost less than Gemini 3.1 Pro or Claude. The pricing recorded in September included an increase scheduled for 1 January 2027, from $0.75/$3.75 to $1.50/$7.50 per million input/output tokens. That would double the cost at the same token usage.

Claude's content filters blocked public-domain Grimm and Tolstoy pages, including on retries. That is a problem for unattended book conversion even when the pages it accepts are transcribed well.

### Hosted OCR services

These figures come from published pricing and benchmarks, rather than our document tests. Scores marked `*` are reported by the vendor for its own product. See [Public benchmarks](#public-benchmarks) for how to interpret them.

| Service | Pricing | olmOCR-Bench | ParseBench |
| --- | --- | --- | --- |
| LlamaParse Cost-effective | $3.75 / 1,000 pages | Not reported | 80.6* |
| LlamaParse Agentic | $12.50 / 1,000 pages | 73.5 | 87.0* |
| LlamaParse Agentic Plus | $56.25 / 1,000 pages | Not reported | 90.2* |
| Reducto r-1 | $10 / 1,000 pages | Not reported | 62.4 |
| Nanonets OCR-3 | $10 / 1,000 pages | 87.4* | Not reported |
| Unsiloed | $10–12 / 1,000 pages; $250 monthly minimum | 88.0* | Not reported |
| Hosted olmOCR 2 | About $0.10–0.20 / million tokens | 82.4 | Not reported |

LlamaParse is a candidate for a comparison on the same documents. Its strong ParseBench scores alone do not establish an advantage over the supported backends. The LlamaParse olmOCR-Bench result above was measured by Unsiloed, a competing service.

## Local models

Local models avoid API charges and can keep documents on the machine. Downloads, memory use and speed matter for long books. Our local tests used the original eight sample files on an M4 Pro with 48 GB of unified memory.

### MinerU 4.0 and PaddleOCR-VL 1.6

MinerU in `standard` mode was the more useful of the two on the scanned samples. PaddleOCR-VL ran faster in parallel and handled equations well, but made more errors on Fraktur and census tables.

| Sample | MinerU standard | PaddleOCR-VL 1.6 |
| --- | --- | --- |
| Equations | Nearly identical to the Datalab output | Best result in this comparison |
| Alice | Dropped the line under an illustration | Dropped the same line |
| Tolstoy | 97.1% reported text accuracy | 98.5% with footnotes enabled; the default omitted them |
| Grimm | Read the long s (`ſ`) as `f` | Failed both keyword checks |
| Shijing | Lost two text columns and the score's title and lyrics | Prose complete; the score remained an image |
| 1880 census | Shifted rows and some digit errors | About 64 of 247 rows differed from Datalab |
| 1980 census | 53 of 56 rows matched Datalab | Shifted rows and misread names |
| Sample checks passed | 7 of 8 | 5 of 8 |

Row agreement with Datalab is not a correctness score: Datalab itself had errors, as the census tests above show.

| Resource or timing | MinerU 4.0 | PaddleOCR-VL 1.6 |
| --- | --- | --- |
| One worker | ~8 seconds per page | ~8 seconds per page with MLX; 27–50 on CPU |
| Best measured throughput | ~7 pages per minute | ~9.5 pages per minute |
| Estimated 300-page book | ~45 minutes | ~32 minutes |
| Memory in the tested setup | ~6.5 GB | ~13 GB |
| Installation download | ~1.4 GB runtime + 2 GB models | ~1.4 GB runtime + 2 GB models |

MinerU's faster `flash` and `basic` modes dropped Cyrillic text. Its `advanced` mode improved census reading but repeatedly got stuck generating the same Chinese character. `standard` is the candidate for a local backend. PaddleOCR-VL's tested setup also had batching crashes and version-dependent equation errors.

### Local model reference

MinerU and PaddleOCR-VL were tested above; the remaining models were assessed from published results and documentation. Download sizes show the full model / smallest listed version where both were recorded. Smaller, quantized versions may have different accuracy. Model links lead to their repositories or model cards, including license terms.

| Model | olmOCR-Bench | OmniDocBench v1.6 | ParseBench | Download | Mac support | License notes |
| --- | --- | --- | --- | --- | --- | --- |
| [Chandra OCR 2](https://github.com/datalab-to/chandra) | 85.8* | Not reported | 70.1 | 10.6 / 3.4 GB | Community MLX and GGUF ports | Free for personal use, research or companies under $2M |
| [dots.mocr](https://github.com/rednote-hilab/dots.mocr) | 83.9* | Not reported | 55.8 | 6.1 / 3.5 GB | Community MLX | MIT with publication-digitisation restrictions |
| [LightOnOCR-2-1B](https://huggingface.co/lightonai/LightOnOCR-2-1B) | 83.2* | Not reported | 48.0 | 2.0 GB | Transformers on MPS | Apache 2.0 |
| [olmOCR 2](https://huggingface.co/allenai/olmOCR-2-7B-1025) | 82.4 | 85.7† | Not reported | 16.6 / 5.6 GB | Community MLX, LM Studio | Apache 2.0 |
| [Marker v2](https://github.com/datalab-to/marker) | 76.0* balanced / 66.6* fast | Not reported | Not reported | 1.4 GB | Official llama.cpp support | Free under $5M |
| [DeepSeek-OCR 2](https://github.com/deepseek-ai/DeepSeek-OCR-2) | 76.3* | 90.3 | 41.2 | 6.8 / 2.6 GB | Community MLX, llama.cpp | Apache 2.0 |
| [MinerU2.5-Pro / MinerU 4.0](https://github.com/opendatalab/MinerU) | Not reported | 95.8 | 72.8 | 2.3 GB + pipeline models | Official | Apache 2.0; commercial license above 100M monthly users or $20M monthly revenue |
| [PaddleOCR-VL 1.6](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL-Apple-Silicon.en.md) | Not reported | 96.3 | 67.4 | 1.9 / 0.7 GB | Official | Apache 2.0 |
| [HunyuanOCR-1.5](https://github.com/Tencent-Hunyuan/HunyuanOCR) | Not reported | 94.7* | 63.9 | 4.6 GB | llama.cpp guide | Tencent license |
| [GLM-OCR](https://github.com/zai-org/GLM-OCR) | 68.4 | 95.2 | 29.6 | 2.7 GB; 2.2 GB via Ollama | MLX, Ollama, llama.cpp | MIT |

`*` Vendor-reported score. LightOnOCR's score excludes headers and footers. `†` The source did not identify the OmniDocBench version for olmOCR 2.

Chandra OCR 2 is worth testing on the same scans before choosing another local model. GLM-OCR is easier to install through Ollama, but its strong OmniDocBench result did not carry over to the other published benchmarks. Mac speed and memory remain unmeasured here for Chandra, dots.mocr, olmOCR 2 and LightOnOCR-2.

## Public benchmarks

Scores belong to their benchmark and test setup. Do not average them into a single ranking or treat small differences from separate runs as proof that one model is better.

- [olmOCR-Bench](https://github.com/allenai/olmocr) tests mostly English documents, including scans, tables and mathematics. Reported scores can use different test versions or omit headers and footers.
- [ParseBench](https://github.com/run-llama/ParseBench/blob/main/leaderboard.csv) covers about 2,000 pages across five areas. It includes general vision models. LlamaIndex, which sells LlamaParse, maintains it.
- [OmniDocBench](https://github.com/opendatalab/OmniDocBench) is widely used for local OCR models. OpenDataLab also develops MinerU. High scores on this benchmark did not predict which model would read our old census scans best.

Specialised tests expose differences that a full-page score can hide. These selected results apply to the tested versions, not automatically to later models with similar names.

| Measure | Selected reported results |
| --- | --- |
| Rewriting unclear text, [FaithC4](https://arxiv.org/html/2607.21617v2); lower is better | Gemini 3 Flash 0.0%; PaddleOCR-VL 1.5 7.9%; olmOCR 2 58.6% |
| Photographed and non-Latin pages, [MDPBench](https://github.com/Yuliang-Liu/MultimodalOCR/tree/main/MDPBench); higher is better | dots.mocr 80.5; Chandra 2 79.7; PaddleOCR-VL 1.6 78.9 |
| Table structure, OmniDocBench v1.6 TEDS; higher is better | PaddleOCR-VL 1.6 94.8; MinerU2.5-Pro 93.4 |
| Formulas, OmniDocBench v1.6 CDM; higher is better | PaddleOCR-VL 1.6 and MinerU2.5-Pro both 97.5 |
| Handwriting character error, [METATR](https://arxiv.org/html/2605.26712v1); lower is better | Gemini 3 Pro 28.5%; Claude Opus 4.5 31.2%; Mistral OCR 43.6% |

## Pricing and additional sources

Use the linked pages for current rates.

- Supported services: [Datalab pricing](https://www.datalab.to/pricing), [Mistral pricing](https://mistral.ai/pricing), [Mistral OCR 4.1](https://docs.mistral.ai/models/ocr-4-1), [OpenAI pricing](https://developers.openai.com/api/docs/pricing).
- Other remote services: [Gemini](https://ai.google.dev/gemini-api/docs/pricing), [Claude](https://platform.claude.com/docs/en/about-claude/pricing), [LlamaParse](https://developers.llamaindex.ai/python/cloud/general/pricing/), [Reducto](https://reducto.ai/pricing), [Unsiloed](https://www.unsiloed.ai/pricing).
- Additional benchmark sources: [Nanonets leaderboard](https://benchmarking.nanonets.com/benchmarks/olmocr), [Datalab benchmarks](https://www.datalab.to/benchmarks), [Unsiloed harness](https://github.com/Unsiloed-AI/unsiloed-olmocr-benchmark), [LightOnOCR paper](https://arxiv.org/html/2601.14251).
