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
        r"^\s*<[^>]+>",  # HTML block
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
