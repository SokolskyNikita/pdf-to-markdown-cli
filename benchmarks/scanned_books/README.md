# Scanned-book benchmark

Sixteen PDF pages from three public-domain books, each with a reference transcription checked against the page image. It measures what the sample tests in `examples/` don't: two-page scans, footnotes, and whether a backend keeps old spellings and misprints exactly as printed.

| File | Pages | What it tests | Source |
| --- | --- | --- | --- |
| `samples/vieira_cartas_pt.pdf` | 8 spreads (16 book pages) | Two facing pages per scan, no text layer. Portuguese letters with superscript abbreviations (`V. Ex.ª`, `Rev.ᵐᵒ`), 28 numbered footnotes, `(sic)`, pre-1945 accents (`êste`, `prègações`, `restituïção`) and printer's errors (`Castslo`, `benegnidade`, `Lisbon`) | Padre António Vieira, *Cartas*, vol. III, ed. J. Lúcio d'Azevedo (Coimbra, 1928), pp. 34–35, 38–39, 236–237, 426–427, 462–463, 536–537, 592–593, 718–719 ([archive.org](https://archive.org/details/tomo-iii_202302)) |
| `samples/multatuli_brieven_nl.pdf` | 5 | Multatuli's own spelling (`zyn`, `myn`, `geloopen`) and his French, mistakes included (`la tonnerre`, `triomfant`, `plûtot`). IA's OCR as a text layer | Multatuli, *Brieven*, vol. 1 (1891), pp. 63, 85, 86, 115, 116 ([archive.org](https://archive.org/details/brievenvanmulta01multgoog)) |
| `samples/sevigne_lettres_fr.pdf` | 3 | 17th-century spelling in the letters (`avoit`, `connoissez`) next to modern spelling in the editor's notes (`étaient`, `avait`), superscript note markers, 19 notes, a margin date. IA's OCR as a text layer | *Lettres de Madame de Sévigné*, vol. 6, ed. Monmerqué (Hachette, 1862), pp. 230–232 ([archive.org](https://archive.org/details/lettresdemadame03monmgoog)) |

All three are public domain: Vieira died in 1697 and his editor in 1933, Multatuli in 1887, and the Sévigné edition was published in 1862.

The Vieira spreads are made by placing two consecutive page scans side by side (`build_samples.py`), because real two-page scans of suitable books are rare. They have no gutter shadow or page curvature. The other two samples are Google's scans with the Internet Archive's own OCR added as an invisible text layer, so a backend that reads the text layer sees realistic OCR errors. `python benchmarks/scanned_books/build_samples.py` rebuilds all three from the Internet Archive.

## Running

```bash
pip install -e ".[dev]"
python benchmarks/scanned_books/run.py --backend datalab --mode accurate
python benchmarks/scanned_books/score.py OUTPUT_DIR
```

`run.py` converts the samples with this checkout and `--paginate`, then scores them. It calls the real API: Datalab `accurate` costs about $0.12, the rest less. Pass `--out DIR` to keep the output and `--json` for machine-readable scores. `score.py` scores any directory of `<sample>.md` files, and `--min-accuracy N` makes it exit 1 below N%.

The scorer reports:

- **Accuracy**: word-level, case- and accent-sensitive. Running heads and page numbers are ignored, superscript notations (`<sup>`, Unicode, LaTeX, `ª`) count as the same, and a block of 4+ words moved elsewhere counts as one error.
- **Footnotes found**: a footnote counts when its opening words appear on its page, ignoring accents and misreadings.
- **Spelling probes**: 42 printed spellings and misprints that must survive verbatim.
- **Order checks**: on each spread, the left page's last footnote must come before the right page's text.
- **Superscripts**: LaTeX and Unicode-modifier superscripts left in the output (pdf-to-md writes `<sup>`).

## Reference files

`reference/<sample>_p<N>.txt` is the transcription of PDF page N (0-based, as `--paginate` numbers it). Each was checked line by line against the page image by Claude (Anthropic's model), starting from Datalab and Mistral drafts. Corrections are welcome.

- `@@` lines are running heads, page numbers and margin dates, and aren't scored. In a spread, the second `@@` line marks where the right-hand page starts.
- `@fn` lines are footnotes.
- `{a|b}` lists acceptable readings where the print is unclear.
- `^x` is a superscript, e.g. `V. Ex.^a`.
- Everything else is exactly as printed, misprints included. An output that "corrects" `benegnidade` to `benignidade` is wrong.

## Baselines

`baselines/<backend>-<mode>/` holds output made on 30 September 2026 with each backend's default settings, and `-split-spreads` folders the same settings with `--split-spreads`. `tests/test_benchmark.py` checks that the scorer still gives them these scores.

| Setting | Accuracy | Spelling | Order | Footnotes (of 47) | $ for 16 pages |
| --- | --- | --- | --- | --- | --- |
| Datalab `accurate` | **99.50%** | 21/42 | **8/8** | 47 | 0.12 |
| Datalab `balanced` | 99.14% | 16/42 | 8/8 | 47 | 0.048 |
| Datalab `fast` | 98.81% | 18/42 | 7/8 | 47 | 0.048 |
| GPT-6 Luna `accurate` | 98.42% | 22/42 | 6/8 | 43 | 0.026 |
| GPT-6 Luna `fast` | 98.38% | **26/42** | 3/8 | 47 | 0.013 |
| Mistral OCR 4.0 | 97.93% | 18/42 | 3/8 | 47 | 0.064 |
| GPT-6 Luna `balanced` | 94.79% | 23/42 | 4/8 | 45 | 0.016 |
| GPT-6 Luna `balanced` via OpenRouter | 94.06% | 21/42 | 4/8 | 45 | same rates as OpenAI |
| Mistral OCR 4.0, `--split-spreads` | 99.07% | 22/42 | 8/8 | 47 | 0.096 |
| GPT-6 Luna `fast`, `--split-spreads` | 98.82% | 26/42 | 8/8 | 47 | 0.011 |
| GPT-6 Luna `balanced`, `--split-spreads` | 98.78% | 26/42 | 8/8 | 47 | 0.016 |
| GPT-6 Luna `balanced` via OpenRouter, `--split-spreads` | 98.76% | 27/42 | 8/8 | 47 | 0.017 |
| GPT-6 Luna `accurate`, `--split-spreads` | 98.46% | 22/42 | 8/8 | 45 | 0.025 |

- Every backend "corrects" some printed spellings: Datalab and Mistral modernise or archaise words, and GPT-Luna fixes misprints. No backend keeps more than 26 of 42.
- On the first spread, GPT-Luna `balanced` transcribed only the left page (282 of 558 words) on both routes. The left page ends mid-sentence just above its footnotes. That one page explains most of the gap between `balanced` and the other modes.
- `--split-spreads` sends each half of a spread as its own page. With it, every GPT-Luna setting and Mistral kept both halves and put every left-page footnote in order (8/8). GPT-Luna cost the same; Mistral, which bills per page, cost 1.5 times as much.
- Without `--split-spreads`, Mistral returns the left page's footnotes of a spread in its `header` field. pdf-to-md adds them back at the end of the page, so they are found but fail the order check.
- LLM results vary between runs; expect a point or two of accuracy and a few probes either way.
