"""The scanned-book benchmark in ``benchmarks/scanned_books``, checked offline.

These guard the fixtures and the scorer: every sample page has a reference,
the references score perfectly against themselves, and the stored baselines
keep the scores recorded when they were made. Converting the samples for real
is ``benchmarks/scanned_books/run.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from docs_to_md.pdf import count_pages

pytest.importorskip("rapidfuzz")
BENCH = Path(__file__).resolve().parent.parent / "benchmarks" / "scanned_books"
if not BENCH.is_dir():  # the sdist ships without the benchmark
    pytest.skip("benchmark fixtures not present", allow_module_level=True)

sys.path.insert(0, str(BENCH))  # score.py imports manifest.py from its own folder
import score  # noqa: E402

# Baseline -> (accuracy, spelling probes kept, order checks passed, footnotes found).
# Update these when a baseline is regenerated or a reference is corrected.
EXPECTED = {
    "datalab-accurate": (99.50, 21, 8, 47),
    "datalab-balanced": (99.14, 16, 8, 47),
    "datalab-fast": (98.81, 18, 7, 47),
    "mistral": (97.93, 18, 3, 47),
    "openai-accurate": (98.42, 22, 6, 43),
    "openai-balanced": (94.79, 23, 4, 45),
    "openai-fast": (98.38, 26, 3, 47),
    "openrouter-balanced": (94.06, 21, 4, 45),
    # The same settings with --split-spreads.
    "mistral-split-spreads": (99.07, 22, 8, 47),
    "openai-accurate-split-spreads": (98.46, 22, 8, 45),
    "openai-balanced-split-spreads": (98.78, 26, 8, 47),
    "openai-fast-split-spreads": (98.82, 26, 8, 47),
    "openrouter-balanced-split-spreads": (98.76, 27, 8, 47),
}


def reference_as_output(out: Path) -> Path:
    """Write each reference as the paginated Markdown a perfect conversion would produce."""
    for sample, pages in score.SAMPLES.items():
        parts = []
        for n in range(pages):
            text = (score.REFERENCE / f"{sample}_p{n}.txt").read_text(encoding="utf-8")
            text = re.sub(r"\{([^{}|]*)\|[^{}]*\}", r"\1", text)
            lines = [re.sub(r"^@fn ", "", line) for line in text.splitlines() if not line.startswith("@@")]
            body = re.sub(r"\^(\w+)", r"<sup>\1</sup>", "\n\n".join(lines))
            parts.append(f"\n\n{{{n}}}{'-' * 48}\n\n{body}")
        (out / f"{sample}.md").write_text("".join(parts), encoding="utf-8")
    return out


def test_every_sample_page_has_a_reference():
    assert sorted(p.stem for p in (BENCH / "samples").glob("*.pdf")) == sorted(score.SAMPLES)
    expected = {f"{s}_p{n}.txt" for s, pages in score.SAMPLES.items() for n in range(pages)}
    assert {p.name for p in score.REFERENCE.glob("*.txt")} == expected
    for sample, pages in score.SAMPLES.items():
        assert count_pages(BENCH / "samples" / f"{sample}.pdf") == pages


def test_spelling_probes_are_in_the_references():
    for sample, n, text in score.SPELLING_PROBES:
        reference = score.Reference(score.REFERENCE / f"{sample}_p{n}.txt")
        assert text in score.flat(score.resolve(reference.text, None)), (sample, n, text)


def test_references_score_perfectly(tmp_path):
    result = score.score(reference_as_output(tmp_path))
    assert result["accuracy"] == 100.0
    assert all(result["probes"].values()) and all(result["order"].values())
    assert len(result["order"]) == score.SAMPLES["vieira_cartas_pt"]
    for sample in result["samples"].values():
        assert sample["footnotes_found"] == sample["footnotes_expected"]


def test_missing_output_scores_zero(tmp_path):
    result = score.score(tmp_path)
    assert result["accuracy"] == 0.0
    assert not any(result["probes"].values())


@pytest.mark.parametrize("baseline", sorted(EXPECTED))
def test_baseline_scores(baseline):
    result = score.score(BENCH / "baselines" / baseline)
    accuracy, probes, order, footnotes = EXPECTED[baseline]
    assert result["accuracy"] == pytest.approx(accuracy, abs=0.05)
    assert sum(result["probes"].values()) == probes
    assert sum(result["order"].values()) == order
    assert sum(s["footnotes_found"] for s in result["samples"].values()) == footnotes


def test_superscript_notations_are_equivalent():
    variants = ["V. Ex.<sup>a</sup> (1)", "V. Ex.ª (1)", "V. Ex.ᵃ ⁽¹⁾", "V. Ex.$^{a}$ (1)", "V. Ex.^a (1)"]
    assert {tuple(score.tokens(score.clean(v.replace("⁽¹⁾", "¹")))) for v in variants} == {("V", "Exa", "1")}


def test_a_moved_block_is_one_error():
    words = ["um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito"]
    moved = words[4:] + words[:4]
    assert score.edit_errors(words, moved) == 1
    assert score.edit_errors(words, words[:4]) == 4
