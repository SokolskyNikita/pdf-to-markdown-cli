# Sample documents

Each PDF here sits next to the real output `pdf-to-md` produced for it: `<name>.md`, plus `<name>_images/` when the document has images. They show what to expect from a conversion, and they're the fixtures for the test suite.

| File | Pages | Language | What makes it hard | Source |
| --- | --- | --- | --- | --- |
| `alice_in_wonderland_sample.pdf` | 3 | English | Illustrated novel pages, curly quotes | Lewis Carroll, *Alice's Adventures in Wonderland* (1865) |
| `equations.pdf` | 1 | English | Dense mathematics, rendered as LaTeX | Algebraic geometry lecture notes |
| `darwin_origin_of_species_en.pdf` | 2 | English | 1859 letterpress scan, fold-out tree diagram | Charles Darwin, *On the Origin of Species*, first edition facsimile, p. 117 and the fold-out diagram |
| `tolstoy_war_and_peace_ru.pdf` | 2 | Russian | Cyrillic mixed with French, translated footnotes, margin line numbers | Leo Tolstoy, *War and Peace*, vol. 1, Complete Works vol. 9 (1937), pp. 13–14 |
| `grimm_fairy_tales_de.pdf` | 2 | German | Fraktur blackletter, 19th-century spelling | Brothers Grimm, *Kinder- und Hausmärchen*, 7th ed., vol. 2 (1857), tale 88 |
| `shijing_gupu_zh.pdf` | 2 | Chinese | Vertical right-to-left classical text, staff notation with numbered notes | Yuan Jiagu (ed.), *Shijing Gupu* (1908 lithograph), preface and first score |
| `census_1880_tables_en.pdf` | 2 | English | Yellowed microfiche scan: two tables side by side, tiny type, dotted leaders, remarks wrapped across rows | US Census Office, *Statistics of the Population at the Tenth Census* (1883), Table III, pp. 245–246 |
| `census_1980_ancestry_en.pdf` | 2 | English | Dense statistical table with two-level column headers, space-separated thousands, `(NA)` cells | US Bureau of the Census, *Ancestry of the Population by State: 1980* (1983), Table 3b |

The census outputs show when each mode is worth it. The 1980 table converts correctly in the default `fast` mode. The 1880 microfiche page uses `--mode accurate`, which removes the dotted leaders and fixes digits that `fast` misreads on this scan (May township 899 instead of 609). The manifest records the mode for each sample.

The Darwin, Tolstoy, Grimm, and Shijing samples are public-domain texts, and the census reports are US government works. They're two-page excerpts of full-book scans, kept small so the repository and the source distribution stay light.

## How the tests use them

- [`tests/samples.py`](../tests/samples.py) lists every sample with its page count, the words a correct conversion must contain, the minimum number of table rows, and the mode, if it isn't the default.
- `tests/test_samples.py` checks, offline, that each PDF opens and splits correctly, and that each committed `.md` file here is complete: it contains the expected words and every image link resolves.
- `tests/test_live.py` converts every sample with the real API, one page per chunk with pagination, then checks the text, page numbering, and images. Run it with `DATALAB_API_KEY=... pytest -m live` when changing anything that affects output.

## Adding a sample

1. Put a short excerpt (one to three pages) of a public-domain document here. It should exercise something the other samples don't.
2. Generate its output: `pdf-to-md examples`, adding `--mode` if the sample needs it. Existing outputs are skipped, so only the new file is converted.
3. Add an entry to `tests/samples.py` and a row to the tables here and in the main README.

To refresh every output after a change in conversion behavior, run `pdf-to-md examples --overwrite` and review the diff.
