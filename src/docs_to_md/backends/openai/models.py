"""OpenAI Responses API request building, response parsing, and pricing.

References:
- https://developers.openai.com/api/docs/guides/file-inputs
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/pricing
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docs_to_md.backends.base import parse_option_value
from docs_to_md.errors import APIError

DEFAULT_MODEL = "gpt-6-luna"
OUTPUT_FORMATS = frozenset({"markdown", "html"})

# --mode -> reasoning effort. Transcription is mostly reading, so even
# "accurate" stays well below the model's maximum effort.
REASONING_EFFORT: dict[str, str] = {"fast": "none", "balanced": "low", "accurate": "medium"}
MODES = tuple(REASONING_EFFORT)
DEFAULT_MODE = "balanced"

# Input extension (without dot) -> MIME type. PDFs are sent as files (the API
# passes the model both the text layer and page images); images are sent as images.
PDF_MIME_TYPE = "application/pdf"
IMAGE_MIME_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
INPUT_MIME_TYPES: dict[str, str] = {"pdf": PDF_MIME_TYPE, **IMAGE_MIME_TYPES}


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens at the standard service tier."""

    input: float
    cached_input: float
    cache_write: float
    output: float


# Standard tier, prompts up to LONG_CONTEXT_TOKENS.
PRICES: dict[str, Price] = {
    "gpt-6-luna": Price(0.10, 0.01, 0.125, 0.50),
    "gpt-5.6-luna": Price(0.20, 0.02, 0.25, 1.20),
}
# Longer prompts cost 2x for input and 1.5x for output, for the whole request.
LONG_CONTEXT_TOKENS = 272_000
# Flex and Batch cost half; other tiers (priority, fast) aren't priced here.
TIER_MULTIPLIERS: dict[str, float] = {"default": 1.0, "auto": 1.0, "flex": 0.5, "batch": 0.5}

_PAGES_SCHEMA = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {"type": "string"}}},
    "required": ["pages"],
    "additionalProperties": False,
}

_FORMAT_RULES = {
    "markdown": """\
- Write Markdown: `#` headings that follow the document's hierarchy, lists, `>`
  block quotes, and `*italic*` / `**bold**` where the page uses them.
- Write tables as GitHub-flavored Markdown tables with every row and cell. If a
  header spans several columns, repeat it in each column it covers.
- Write mathematics as LaTeX: `$...$` inline and `$$...$$` for display equations.""",
    "html": """\
- Write each page as an HTML fragment (no <html>, <head>, or <body>) using
  semantic tags: <h1>-<h6>, <p>, <ul>/<ol>, <blockquote>, <em>, <strong>, <sup>.
- Write tables as <table> with every row and cell; use colspan and rowspan for
  spanning headers.
- Write mathematics as LaTeX inside <math> elements, with display="block" for
  display equations.""",
}

_FIGURE_RULES = {
    True: "- Replace each illustration, photo, chart, or diagram with a one-sentence description"
    " in italics, in square brackets. Keep any printed caption as text.",
    False: "- Leave out illustrations, photos, charts, and diagrams, but keep their printed captions.",
}

INSTRUCTIONS = """\
You transcribe document pages into {format_name}. Return JSON whose "pages" array
has exactly one string per input page, in order: {page_count} page{plural}. Never
merge, split, skip, or reorder pages. A blank page is an empty string.

Transcribe faithfully:
- Copy every word of the body text exactly as printed, in its original language,
  script, spelling, and punctuation. Do not translate, modernize, correct,
  summarize, or add commentary.
- Follow the reading order: columns in order, and vertical text (as in Chinese
  or Japanese) written out as horizontal lines in its reading order.
- Leave out running headers, running footers, page numbers, library stamps, and
  scanning artifacts.
- Write each paragraph as one line of text. Rejoin words hyphenated across line
  breaks, and keep line breaks only where they matter, as in verse.
- Put footnotes at the end of the page they appear on, with their markers.
{format_rules}
{figure_rules}"""


def instructions_for(output_format: str, page_count: int, describe_figures: bool) -> str:
    return INSTRUCTIONS.format(
        format_name="Markdown" if output_format == "markdown" else "HTML",
        page_count=page_count,
        plural="s" * (page_count != 1),
        format_rules=_FORMAT_RULES[output_format],
        figure_rules=_FIGURE_RULES[describe_figures],
    )


@dataclass
class TranscribeRequest:
    """Everything needed to build one /responses request body."""

    model: str
    output_format: str
    page_count: int
    reasoning_effort: str
    describe_figures: bool = True
    extra: dict[str, str] | None = None

    def body(self, path: Path) -> dict[str, Any]:
        mime_type = INPUT_MIME_TYPES.get(path.suffix.lower().lstrip("."))
        if not mime_type:
            raise APIError(f"Unsupported file type: {path.name}")
        data_url = f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode()}"
        if mime_type == PDF_MIME_TYPE:
            part = {"type": "input_file", "filename": path.name, "file_data": data_url, "detail": "high"}
        else:
            part = {"type": "input_image", "image_url": data_url, "detail": "high"}
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions_for(self.output_format, self.page_count, self.describe_figures),
            "input": [{"role": "user", "content": [part]}],
            "reasoning": {"effort": self.reasoning_effort},
            "text": {
                "format": {"type": "json_schema", "name": "pages", "strict": True, "schema": _PAGES_SCHEMA}
            },
            "store": False,
        }
        body.update({key: parse_option_value(value) for key, value in (self.extra or {}).items()})
        return body


@dataclass
class TranscribeResult:
    pages: list[str]
    cost_cents: float | None = None


def cost_cents(model: str, usage: dict[str, Any], service_tier: str | None) -> float | None:
    """What a response cost, or None for models and tiers without a known price."""
    if isinstance(usage.get("cost"), (int, float)):
        return float(usage["cost"]) * 100  # OpenRouter reports the charge in dollars
    # Responses may name a dated snapshot, e.g. gpt-6-luna-2026-05-18.
    price = PRICES.get(model) or next((p for name, p in PRICES.items() if model.startswith(f"{name}-")), None)
    multiplier = TIER_MULTIPLIERS.get(service_tier or "default")
    if price is None or multiplier is None:
        return None
    details = usage.get("input_tokens_details") or {}
    total_input = int(usage.get("input_tokens") or 0)
    cached = int(details.get("cached_tokens") or 0)
    written = int(details.get("cache_write_tokens") or 0)
    uncached = max(0, total_input - cached - written)
    input_multiplier, output_multiplier = (2.0, 1.5) if total_input > LONG_CONTEXT_TOKENS else (1.0, 1.0)
    dollars = (
        input_multiplier
        * (uncached * price.input + cached * price.cached_input + written * price.cache_write)
        + output_multiplier * int(usage.get("output_tokens") or 0) * price.output
    ) / 1_000_000
    return dollars * multiplier * 100


def parse_response(data: dict[str, Any], requested_model: str) -> TranscribeResult:
    """Extract the page list from a /responses payload, or raise ``APIError``."""
    status = data.get("status")
    if status == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason") or "unknown reason"
        hint = " (try a smaller --chunk-size)" if reason == "max_output_tokens" else ""
        raise APIError(f"the model stopped early: {reason}{hint}")
    if status != "completed":
        error = data.get("error") or {}
        raise APIError(f"response {status or 'missing status'}: {error.get('message') or 'no details'}")

    texts: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "refusal":
                raise APIError(f"the model refused: {part.get('refusal') or 'no reason given'}")
            if part.get("type") == "output_text":
                texts.append(part.get("text") or "")
    try:
        pages = json.loads("".join(texts))["pages"]
    except (ValueError, KeyError, TypeError) as e:
        raise APIError(f"the model returned malformed output ({e})") from e
    if not isinstance(pages, list) or not all(isinstance(page, str) for page in pages):
        raise APIError("the model returned malformed output (pages is not a list of strings)")

    model = str(data.get("model") or requested_model)
    return TranscribeResult(
        pages=pages,
        cost_cents=cost_cents(model, data.get("usage") or {}, data.get("service_tier")),
    )
