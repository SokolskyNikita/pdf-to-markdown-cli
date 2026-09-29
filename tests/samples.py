"""Manifest of the sample documents in ``examples/``.

Each entry records the page count and words that a correct conversion must
contain. Offline tests check the PDFs themselves; the live tests (``pytest -m
live``) convert them with the real API and check the output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@dataclass(frozen=True)
class Sample:
    filename: str
    pages: int
    language: str
    keywords: tuple[str, ...]
    has_images: bool
    challenge: str
    mode: str | None = None  # --mode used for the reference output and live test
    min_table_rows: int = 0  # Markdown table rows a correct conversion must contain

    @property
    def path(self) -> Path:
        return EXAMPLES / self.filename


SAMPLES = (
    Sample(
        "alice_in_wonderland_sample.pdf",
        3,
        "en",
        ("Cat", "Alice"),
        True,
        "illustrated novel with curly quotes",
    ),
    Sample("equations.pdf", 1, "en", ("COROLLARY",), True, "mathematics rendered as LaTeX"),
    Sample(
        "darwin_origin_of_species_en.pdf",
        2,
        "en",
        ("natural selection", "varieties"),
        True,
        "1859 scan with the fold-out tree diagram",
    ),
    Sample(
        "tolstoy_war_and_peace_ru.pdf",
        2,
        "ru",
        ("Анны Павловны", "vicomte"),
        False,
        "Cyrillic text mixed with French, footnotes, and margin line numbers",
    ),
    Sample(
        "grimm_fairy_tales_de.pdf",
        2,
        "de",
        ("Löweneckerchen", "Vater"),
        False,
        "1857 Fraktur blackletter typeface",
    ),
    Sample(
        "shijing_gupu_zh.pdf",
        2,
        "zh",
        ("古詩", "皇皇者華"),
        True,
        "1908 lithograph: vertical right-to-left text and music notation",
    ),
    Sample(
        "census_1880_tables_en.pdf",
        2,
        "en",
        ("Marshall township", "1,910", "Lesterville"),
        False,
        "yellowed microfiche: side-by-side tables, dotted leaders, wrapped remarks",
        mode="accurate",
        min_table_rows=100,
    ),
    Sample(
        "census_1980_ancestry_en.pdf",
        2,
        "en",
        ("Albanian", "16 971", "Middle Atlantic"),
        False,
        "dense statistical table with two-level column headers",
        min_table_rows=100,
    ),
)
