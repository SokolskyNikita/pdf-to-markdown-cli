#!/usr/bin/env python3
"""Score pdf-to-md Markdown output against the reference transcriptions in ``reference/``.

Usage:
    python benchmarks/scanned_books/score.py OUTPUT_DIR [--json] [--min-accuracy 97]

OUTPUT_DIR holds ``<sample>.md`` for each PDF in ``samples/``, converted with
``--paginate`` (pages are split on the ``{N}------`` separators). Missing files
or pages score 0.

Reference files (``reference/<sample>_p<N>.txt``, N = 0-based PDF page):

- ``@@`` lines are running heads, page numbers and margin dates. They aren't
  scored, whether the output keeps or drops them. In a two-page spread the
  second ``@@`` line marks where the right-hand page starts.
- ``@fn`` lines are footnotes.
- ``{a|b}`` lists acceptable readings; ``^x`` is a superscript.
- Everything else is the text exactly as printed, misprints included.

Reported, per sample and overall:

- word accuracy: 1 - word edits / reference words, case- and accent-sensitive.
  Superscript notation (<sup>, Unicode, LaTeX, ª/º), quote style, dashes and
  punctuation are normalised away. A moved block of 4+ words counts as one error.
- footnotes found: a footnote counts when its first words appear on its page.
- spelling probes: printed spellings and misprints that must survive verbatim.
- order checks: on each spread, the left page's last footnote must come before
  the right page's text.
- superscript format: counts of LaTeX and Unicode-modifier superscripts left.

Requires: pip install rapidfuzz
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from manifest import SAMPLES, SPELLING_PROBES, SPREADS
from rapidfuzz.distance import Levenshtein

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference"
SUPERSCRIPT_LETTERS = str.maketrans(
    {"ª": "a", "º": "o", "°": "o", "ᵃ": "a", "ᵒ": "o", "ᵐ": "m", "ʳ": "r", "ᵉ": "e", "ᵈ": "d", "ᶜ": "c"}
    | {"ⁱ": "i", "ᵗ": "t", "ˢ": "s", "ⁿ": "n"}
)
SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MODIFIER_LETTERS = re.compile(r"[ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ]")
LATEX_SUPERSCRIPT = re.compile(r"\$\^\{?[^$]*\}?\$")
PAGE_SEPARATOR = re.compile(r"^\{(\d+)\}-{10,}\s*$", re.MULTILINE)
FOOTNOTE_WORDS = 6  # leading words of a footnote that must be found
ORDER_WORDS = 5


def split_pages(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    parts = PAGE_SEPARATOR.split(path.read_text(encoding="utf-8"))
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def clean(text: str) -> str:
    """Strip Markdown/HTML to plain text and unify superscript notation as ^x."""
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^" + m.group().translate(SUPERSCRIPT_DIGITS), text)
    text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\$\^\{?([^$}]*)\}?\$", r"^\1", text)
    text = re.sub(r"[*_#`]|^\s*>|\|", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+([,.;:!?)])", r"\1", text)
    text = text.translate(str.maketrans("“”„‘’`", "\"\"\"'''"))
    text = re.sub(r"\.{4,}|…{2,}", "....", text).replace("…", "...")
    return unicodedata.normalize("NFC", text)


def flat(text: str) -> str:
    """Single-spaced cleaned text, for substring probes."""
    return " ".join(clean(text).replace("\\$", "$").split())


class Reference:
    """One reference page: body text, footnotes, and where a spread's right page starts."""

    def __init__(self, path: Path):
        self.lines: list[tuple[str, str]] = []  # (kind, text); kind is head, fn or body
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("@@"):
                self.lines.append(("head", line[2:].strip()))
            elif line.startswith("@fn "):
                self.lines.append(("fn", line[4:]))
            elif line.strip():
                self.lines.append(("body", line))
        heads = [text for kind, text in self.lines if kind == "head"]
        self.head_tokens = {re.sub(r"[^\w-]", "", word) for head in heads for word in head.split()}
        self.page_numbers = {
            word for head in heads for word in head.split() if re.fullmatch(r"\d{1,4}", word)
        }

    @property
    def text(self) -> str:
        return "\n".join(text for kind, text in self.lines if kind != "head")

    @property
    def footnotes(self) -> list[str]:
        return [text for kind, text in self.lines if kind == "fn"]

    def spread_halves(self) -> tuple[list[str], str | None]:
        """The left page's footnotes and the right page's first body line."""
        heads = [i for i, (kind, _) in enumerate(self.lines) if kind == "head"]
        if len(heads) < 2:
            return [], None
        split = heads[1]
        left_notes = [text for kind, text in self.lines[:split] if kind == "fn"]
        right_body = next((text for kind, text in self.lines[split:] if kind == "body"), None)
        return left_notes, right_body


def resolve(text: str, hypothesis: str | None) -> str:
    """Pick, for each {a|b} in the reference, the reading the output used."""
    hyp = flat(hypothesis) if hypothesis else ""

    def pick(match: re.Match) -> str:
        options = match.group(1).split("|")
        return next((option for option in options if option in hyp), options[0])

    return re.sub(r"\{([^{}]*\|[^{}]*)\}", pick, text)


def tokens(text: str, head_tokens: set[str] = frozenset(), page_numbers: set[str] = frozenset()) -> list[str]:
    text = unicodedata.normalize("NFC", text).replace("​", "").replace("﻿", "").replace("\\$", "$")
    kept = []
    for line in text.splitlines():
        words = line.split()
        is_head = words and any(w in page_numbers for w in words if re.fullmatch(r"\d{1,4}", w))
        if is_head and all(
            re.sub(r"[^\w-]", "", w) in head_tokens or not re.sub(r"\W", "", w) for w in words
        ):
            continue  # running head or page number
        kept.append(line)
    text = " ".join(kept)
    text = re.sub(
        r"[ªºᵃᵒᵐʳᵉᵈᶜⁱᵗˢⁿ]+", lambda m: "^" + m.group().translate(SUPERSCRIPT_LETTERS), text
    ).replace("°", "^o")
    text = re.sub(r"\^(\d+)", r" \1", text)  # footnote markers become their own token
    text = re.sub(r"\.?\s?\^([A-Za-zê]+)", r"\1", text)  # Ex.^a / Exª / Ex.ª -> Exa
    text = text.replace("^", "")
    text = re.sub(r"\b([A-Za-z]{1,6})\.([a-zê]{1,4})\b", r"\1\2", text)  # Rev.ma -> Revma
    text = re.sub(r"(\w')\s+(?=\w)", r"\1", text)  # d' Abril -> d'Abril
    text = re.sub(r"[\\/]", "", text)
    text = re.sub(r"[\"“”„«»‹›]", "", text)
    text = re.sub(r"\s[–—-]+\s", " ", text)
    text = re.sub(r"^[–—-]+\s|\s[–—-]+$", " ", text)
    text = re.sub(r"\.{2,}|…", " ", text)
    text = re.sub(r"[.,;:!?()\[\]{}|*_#]", " ", text)
    return [word for word in text.split() if word.strip("-'")]


def _runs(positions: list[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for position in positions:
        if runs and position == runs[-1][1]:
            runs[-1] = (runs[-1][0], position + 1)
        else:
            runs.append((position, position + 1))
    return [run for run in runs if run[1] - run[0] >= 4]


def edit_errors(reference: list[str], hypothesis: list[str]) -> int:
    """Word edits, counting a block of 4+ words moved elsewhere as one error."""
    ops = Levenshtein.editops(reference, hypothesis)
    inserted = [" ".join(hypothesis[a:b]) for a, b in _runs([o.dest_pos for o in ops if o.tag == "insert"])]
    moved = 0
    for a, b in _runs([o.src_pos for o in ops if o.tag == "delete"]):
        segment = " ".join(reference[a:b])
        for k, block in enumerate(inserted):
            if block and (
                segment in block
                or (len(segment) > 20 and Levenshtein.normalized_similarity(segment, block) > 0.85)
            ):
                moved += (b - a) * 2 - 1
                inserted[k] = ""
                break
    return len(ops) - moved


def _loose(words: list[str]) -> str:
    """Words joined, without accents or case, for finding text despite misreadings."""
    text = unicodedata.normalize("NFD", " ".join(words).casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def find(needle: list[str], haystack: list[str], threshold: float = 0.8) -> int:
    """Start of the run of ``haystack`` most like ``needle``, or -1 if none is close.

    Compares characters, ignoring accents and case, so a footnote counts as found
    despite OCR slips ("Bandirra" for "Bandarra"); spelling is the probes' job.
    """
    if not needle:
        return -1
    target = _loose(needle)
    best, best_index = threshold, -1
    for i in range(max(1, len(haystack) - len(needle) + 1)):
        similarity = Levenshtein.normalized_similarity(target, _loose(haystack[i : i + len(needle)]))
        if similarity >= best:
            if similarity == 1:
                return i
            best, best_index = similarity, i
    return best_index


def score(output_dir: Path, reference_dir: Path = REFERENCE) -> dict:
    result: dict = {"samples": {}, "probes": {}, "order": {}, "superscripts": {}}
    total_words = total_errors = 0
    for sample, page_count in SAMPLES.items():
        output = output_dir / f"{sample}.md"
        pages = split_pages(output)
        words = errors = notes_found = notes_expected = 0
        for n in range(page_count):
            ref = Reference(reference_dir / f"{sample}_p{n}.txt")
            hyp = pages.get(n)
            ref_tokens = tokens(resolve(ref.text, hyp), ref.head_tokens, ref.page_numbers)
            hyp_tokens = tokens(clean(hyp), ref.head_tokens, ref.page_numbers) if hyp else []
            words += len(ref_tokens)
            errors += edit_errors(ref_tokens, hyp_tokens) if hyp else len(ref_tokens)
            for note in ref.footnotes:
                notes_expected += 1
                notes_found += find(tokens(resolve(note, hyp))[:FOOTNOTE_WORDS], hyp_tokens) >= 0
            if sample in SPREADS:
                left_notes, right_body = ref.spread_halves()
                if left_notes and right_body:
                    note = find(tokens(resolve(left_notes[-1], hyp))[:ORDER_WORDS], hyp_tokens)
                    body = find(tokens(resolve(right_body, hyp))[:ORDER_WORDS], hyp_tokens)
                    result["order"][f"{sample}/p{n}"] = 0 <= note < body
        raw = output.read_text(encoding="utf-8") if output.exists() else ""
        result["samples"][sample] = {
            "pages": len(pages),
            "reference_words": words,
            "errors": errors,
            "accuracy": round(100 * (1 - errors / words), 2) if words else 0.0,
            "footnotes_found": notes_found,
            "footnotes_expected": notes_expected,
        }
        result["superscripts"][sample] = {
            "latex": len(LATEX_SUPERSCRIPT.findall(raw)),
            "unicode_modifier_letters": len(MODIFIER_LETTERS.findall(raw)),
        }
        total_words += words
        total_errors += errors
    result["accuracy"] = round(100 * (1 - total_errors / total_words), 2)
    flat_pages = {sample: split_pages(output_dir / f"{sample}.md") for sample in SAMPLES}
    for sample, n, text in SPELLING_PROBES:
        result["probes"][f"{sample}/p{n}: {text}"] = text in flat(flat_pages[sample].get(n, ""))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.add_argument(
        "--min-accuracy", type=float, help="exit 1 if overall accuracy is below this percentage"
    )
    args = parser.parse_args()

    result = score(args.output_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        header = f"{'sample':22} {'pages':>5} {'accuracy':>9} {'errors':>7} {'footnotes':>10}"
        print(f"{header}  superscripts (LaTeX/Unicode)")
        for name, r in result["samples"].items():
            s = result["superscripts"][name]
            footnotes = f"{r['footnotes_found']}/{r['footnotes_expected']}"
            print(
                f"{name:22} {r['pages']:>5} {r['accuracy']:>8.2f}% {r['errors']:>7} {footnotes:>10}"
                f"  {s['latex']}/{s['unicode_modifier_letters']}"
            )
        print(f"OVERALL accuracy {result['accuracy']:.2f}%")
        for label, key, failed in (
            ("spelling probes", "probes", "MISSING"),
            ("order checks", "order", "FAIL"),
        ):
            checks = result[key]
            print(f"{label}: {sum(checks.values())}/{len(checks)}")
            for name, ok in checks.items():
                if not ok:
                    print(f"  {failed:8} {name}")
    if args.min_accuracy is not None and result["accuracy"] < args.min_accuracy:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
