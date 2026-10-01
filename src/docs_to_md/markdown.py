"""Markdown post-processing applied to converted output."""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s{0,3}(?:`{3,}|~{3,})")
_STRUCTURE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^\s{0,3}#{1,6}\s",  # ATX heading
        r"^\s{0,3}>",  # blockquote
        r"^\s{0,3}[*+-]\s+",  # unordered list
        r"^\s{0,3}\d+[.)]\s+",  # ordered list
        r"^\s{0,3}\[[^\]]+\]:\s+\S+",  # link reference definition
        r"^\s{0,3}(?:=+|-+)\s*$",  # setext heading underline
        r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$",  # thematic break
        r"^\s*\|.*\|\s*$",  # table row
        r"^\s*<(?!/?su[pb]>)[^>]+>",  # HTML block (a footnote starting with <sup> is prose)
        r"^\s*\$\$",  # display math
    )
)
_SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")
_MIN_AVERAGE_LINE_LENGTH = 35


def _is_structure_line(line: str) -> bool:
    if line.startswith(("\t", "    ")):
        return True
    return any(pattern.match(line) for pattern in _STRUCTURE_PATTERNS)


def _is_wrapped_paragraph(lines: list[str]) -> bool:
    """Heuristic: does this block look like one paragraph hard-wrapped by OCR?"""
    if len(lines) < 2 or any(_is_structure_line(line) for line in lines):
        return False
    # Respect explicit Markdown hard breaks.
    if any(line.endswith("  ") or line.rstrip().endswith("\\") for line in lines[:-1]):
        return False
    lengths = [len(line.strip()) for line in lines]
    if sum(lengths) / len(lengths) < _MIN_AVERAGE_LINE_LENGTH:
        return False
    # A wrapped paragraph has at least one non-final line that does not end a sentence.
    return any(not _SENTENCE_END.search(line.strip()) for line in lines[:-1])


_IMAGE_THEN_CAPTION = re.compile(r"^(!\[(?P<alt>[^\]\n]+)\]\([^)\n]+\))\n\n(?P=alt)[ \t]*$", re.MULTILINE)


def remove_duplicate_captions(content: str) -> str:
    """Drop a paragraph that only repeats the preceding image's alt text.

    The API emits generated image descriptions both as alt text and as a
    paragraph under the image; the alt text alone keeps the information.
    """
    return _IMAGE_THEN_CAPTION.sub(lambda m: m.group(1), content)


# Unicode superscript digits and modifier letters -> plain characters. The
# ordinal indicators ª and º are ordinary letters (1º, 4ª série) and stay.
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ"
_PLAIN = str.maketrans(_SUPERSCRIPTS, "0123456789abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVW")
_UNICODE_SUPERSCRIPT = re.compile(f"[{_SUPERSCRIPTS}]+")
# Math that is nothing but a superscript: $^{a}$, $^1$, $^{\text{mo}}$, ${}^{2}$.
_LATEX_SUPERSCRIPT = re.compile(
    r"\$(?:\{\})?\^(?:\{\s*(?:\\(?:text|textrm|mathrm|rm)\s*\{)?([^${}\\\n]{1,12}?)\}?\s*\}|([^\s${}\\]))\$"
)


def normalize_superscripts(content: str) -> str:
    """Write superscripts as ``<sup>`` outside code blocks, whatever the backend used.

    Datalab writes ``<sup>a</sup>``, Mistral ``$^{a}$``, and LLMs often use
    Unicode (``Ex.ᵐᵒ``, ``¹``). Other math is left alone.
    """

    def convert(text: str) -> str:
        text = _LATEX_SUPERSCRIPT.sub(lambda m: f"<sup>{(m.group(1) or m.group(2)).strip()}</sup>", text)
        return _UNICODE_SUPERSCRIPT.sub(lambda m: f"<sup>{m.group().translate(_PLAIN)}</sup>", text)

    output: list[str] = []
    prose: list[str] = []
    in_fence = False
    for line in content.splitlines(keepends=True):
        fence = bool(_FENCE.match(line))
        if in_fence or fence:
            output.append(convert("".join(prose)))
            prose.clear()
            output.append(line)
            in_fence ^= fence
        else:
            prose.append(line)
    output.append(convert("".join(prose)))
    return "".join(output)


def normalize_line_breaks(content: str) -> str:
    """Join paragraph lines that were hard-wrapped, leaving real structure alone."""
    if not content:
        return content

    output: list[str] = []
    block: list[str] = []
    in_fence = False

    def flush() -> None:
        if _is_wrapped_paragraph(block):
            output.append(" ".join(line.strip() for line in block))
        else:
            output.extend(block)
        block.clear()

    for line in content.splitlines():
        if _FENCE.match(line):
            flush()
            output.append(line)
            in_fence = not in_fence
        elif in_fence:
            output.append(line)
        elif not line.strip():
            flush()
            output.append(line)
        else:
            block.append(line)
    flush()

    result = "\n".join(output)
    return result + "\n" if content.endswith("\n") else result
