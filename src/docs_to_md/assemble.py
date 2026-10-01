"""Combine per-chunk backend results into one output document plus images."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from docs_to_md.errors import ResultProcessingError
from docs_to_md.markdown import normalize_line_breaks, normalize_superscripts, remove_duplicate_captions

logger = logging.getLogger(__name__)

# Output format -> file extension
OUTPUT_EXTENSIONS: dict[str, str] = {
    "markdown": ".md",
    "html": ".html",
    "json": ".json",
}

_MD_PAGE_DASHES = "-" * 48
_MD_PAGE_MARKER = re.compile(r"^\{(\d+)\}(-{48})$", re.MULTILINE)
_HTML_PAGE_ID = re.compile(r'(data-page-id=")(\d+)(")')
_BLOCK_ID = re.compile(r"(^|['\"])/page/(\d+)/")  # block ids and <content-ref src='/page/N/...'>
_PAGE_ANCHOR = re.compile(r"""(id=["']page-|\(#page-)(\d+)(-)""")  # <span id="page-N-M">, (#page-N-M)
_HTML_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)
_HTML_HEAD = re.compile(r"<head[^>]*>.*?</head>", re.DOTALL | re.IGNORECASE)


@dataclass
class ChunkOutput:
    """The result of converting one chunk.

    ``content`` follows Marker's output conventions, with page numbers local to
    the chunk (0 is its first page): Markdown ``{N}`` + 48 dashes separators and
    ``page-N-M`` anchors, HTML ``data-page-id``, and JSON ``/page/N/`` block ids
    and ``page`` fields. Images are referenced by their key in ``images``.
    """

    pages: Sequence[int]  # source page numbers covered by this chunk, in order
    content: Any  # str for markdown/html, dict for json
    images: dict[str, str] = field(default_factory=dict)  # name -> base64
    page_count: int = 0
    cost_cents: float = 0.0


def join_pages(pages: list[str], output_format: str, paginate: bool) -> str:
    """Combine per-page text using Marker's conventions, with chunk-local page numbers."""
    if output_format == "html":
        divs = "".join(
            f'<div class="page" data-page-id="{i}">\n{page.strip()}\n</div>\n' for i, page in enumerate(pages)
        )
        head = '<head><meta charset="utf-8"/></head>'
        return f"<!DOCTYPE html>\n<html>\n{head}\n<body>\n{divs}</body>\n</html>\n"
    if paginate:
        return "".join(f"\n\n{{{i}}}{_MD_PAGE_DASHES}\n\n{page.strip()}" for i, page in enumerate(pages))
    return "\n\n".join(page.strip() for page in pages if page.strip())


def failed_pages(pages: Sequence[int], reason: str, output_format: str, paginate: bool) -> ChunkOutput:
    """A stand-in for pages whose conversion failed (``--keep-partial``): a comment per page."""
    reason = re.sub(r"-{2,}", "-", " ".join(reason.split()))  # "--" would end the comment
    texts = [f"<!-- pdf-to-md: page {page} failed: {reason} -->" for page in pages]
    return ChunkOutput(pages=pages, content=join_pages(texts, output_format, paginate))


@dataclass
class Document:
    """A fully assembled conversion ready to be written to disk."""

    text: str
    images: dict[str, bytes]


def _page_mapper(pages: Sequence[int]) -> Callable[[int], int]:
    """Map a page number local to a chunk back to the source document."""
    offset = pages[0] if pages else 0

    def mapped(local: int) -> int:
        return pages[local] if 0 <= local < len(pages) else local + offset

    return mapped


def _unique_image_name(name: str, chunk_index: int, used: set) -> str:
    base = Path(name).name or f"image_{len(used)}"
    candidate = base
    if candidate in used:
        candidate = f"chunk{chunk_index + 1}_{base}"
    counter = 2
    while candidate in used:
        candidate = f"chunk{chunk_index + 1}_{counter}_{base}"
        counter += 1
    used.add(candidate)
    return candidate


def _renumber_anchors(text: str, page: Callable[[int], int]) -> str:
    return _PAGE_ANCHOR.sub(lambda m: f"{m.group(1)}{page(int(m.group(2)))}{m.group(3)}", text)


def _rewrite_markdown(text: str, refs: dict[str, str], page: Callable[[int], int]) -> str:
    for old, new in refs.items():
        text = text.replace(f"]({old})", f"]({new})")
    text = _renumber_anchors(text, page)
    return _MD_PAGE_MARKER.sub(lambda m: f"{{{page(int(m.group(1)))}}}{m.group(2)}", text)


def _rewrite_html(text: str, refs: dict[str, str], page: Callable[[int], int]) -> str:
    for old, new in refs.items():
        text = text.replace(f'src="{old}"', f'src="{new}"')
    text = _renumber_anchors(text, page)
    return _HTML_PAGE_ID.sub(lambda m: f"{m.group(1)}{page(int(m.group(2)))}{m.group(3)}", text)


def _rewrite_json(node: Any, refs: dict[str, str], page: Callable[[int], int]) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in ("page", "page_id") and isinstance(value, int):
                out[key] = page(value)
            elif key == "failed_pages" and isinstance(value, list):
                out[key] = [page(v) if isinstance(v, int) else v for v in value]
            else:
                out[key] = _rewrite_json(value, refs, page)
        return out
    if isinstance(node, list):
        return [_rewrite_json(item, refs, page) for item in node]
    if isinstance(node, str):
        node = _BLOCK_ID.sub(lambda m: f"{m.group(1)}/page/{page(int(m.group(2)))}/", node)
        if "src=" in node:
            node = _rewrite_html(node, refs, lambda p: p)
        return node
    return node


def _merge_html(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    head_match = _HTML_HEAD.search(parts[0])
    head = head_match.group(0) if head_match else '<head><meta charset="utf-8"/></head>'
    bodies = []
    for part in parts:
        body = _HTML_BODY.search(part)
        bodies.append((body.group(1) if body else part).strip("\n"))
    return "<!DOCTYPE html>\n<html>\n" + head + "\n<body>\n" + "\n".join(bodies) + "\n</body>\n</html>\n"


def _merge_json(parts: list[dict[str, Any]]) -> dict[str, Any]:
    if len(parts) == 1:
        return parts[0]
    merged: dict[str, Any] = {k: v for k, v in parts[0].items() if k not in ("children", "metadata")}
    merged["children"] = [child for part in parts for child in part.get("children") or []]
    metadata: dict[str, Any] = {}
    for part in parts:
        for key, value in (part.get("metadata") or {}).items():
            if isinstance(value, list):
                metadata.setdefault(key, []).extend(value)
            else:
                metadata.setdefault(key, value)
    merged["metadata"] = metadata
    return merged


def assemble(
    chunks: Sequence[ChunkOutput],
    output_format: str,
    images_dir_name: str,
    reflow_markdown: bool = True,
    superscripts: bool = True,
) -> Document:
    """Merge chunk outputs in order, renaming images and renumbering pages."""
    if not chunks:
        raise ResultProcessingError("No chunk results to assemble")

    used_names: set = set()
    images: dict[str, bytes] = {}
    parts: list[Any] = []

    for index, chunk in enumerate(chunks):
        if chunk.content is None:
            raise ResultProcessingError(f"The API returned no {output_format} content")
        refs: dict[str, str] = {}
        for name, b64 in chunk.images.items():
            try:
                data = base64.b64decode(b64, validate=False)
            except (binascii.Error, ValueError) as e:
                logger.warning("Skipping undecodable image %s: %s", name, e)
                continue
            new_name = _unique_image_name(name, index, used_names)
            images[new_name] = data
            refs[name] = quote(f"{images_dir_name}/{new_name}")

        page = _page_mapper(chunk.pages)
        if output_format == "markdown":
            text = remove_duplicate_captions(_rewrite_markdown(chunk.content, refs, page))
            if superscripts:
                text = normalize_superscripts(text)
            if reflow_markdown:
                text = normalize_line_breaks(text)
            parts.append(text.strip("\n"))
        elif output_format == "html":
            parts.append(_rewrite_html(chunk.content, refs, page))
        elif output_format == "json":
            parts.append(_rewrite_json(chunk.content, refs, page))
        else:
            raise ResultProcessingError(f"Unsupported output format: {output_format}")

    if output_format == "markdown":
        text = "\n\n".join(parts) + "\n"
    elif output_format == "html":
        text = _merge_html(parts)
    else:
        text = json.dumps(_merge_json(parts), indent=2, ensure_ascii=False) + "\n"
    return Document(text=text, images=images)


def write_document(doc: Document, output: Path, images_dir: Path) -> None:
    """Write ``doc`` atomically, replacing any previous output and images."""
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.name}.partial")
    staging = images_dir.with_name(f".{images_dir.name}.partial")
    try:
        if doc.images:
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            for name, data in doc.images.items():
                (staging / name).write_bytes(data)
        partial.write_text(doc.text, encoding="utf-8", newline="\n")  # same bytes on every OS

        if images_dir.exists():
            shutil.rmtree(images_dir)
        if doc.images:
            os.replace(staging, images_dir)
        os.replace(partial, output)
    except OSError as e:
        raise ResultProcessingError(f"Could not write {output}: {e}") from e
    finally:
        partial.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
