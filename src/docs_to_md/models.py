"""Datalab Convert API data types and supported format tables.

Reference: https://documentation.datalab.to/api-reference/convert-document
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODES = ("fast", "balanced", "accurate")

# Output format -> file extension
SUPPORTED_FORMAT_EXTENSIONS: dict[str, str] = {
    "markdown": ".md",
    "json": ".json",
    "html": ".html",
}

# Input extension (without dot) -> MIME type sent to the API.
# https://documentation.datalab.to/docs/common/supportedfiletypes
INPUT_MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "epub": "application/epub+zip",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}

SUPPORTED_INPUT_EXTENSIONS = frozenset(INPUT_MIME_TYPES)
SUPPORTED_MIME_TYPES = frozenset(INPUT_MIME_TYPES.values())


@dataclass
class ConvertOptions:
    """Form fields sent with every /convert request.

    ``page_range`` and ``max_pages`` are only sent for files the CLI does not
    split itself; for PDFs the page selection happens locally.
    """

    output_format: str = "markdown"
    mode: str | None = None
    paginate: bool = False
    disable_image_extraction: bool = False
    disable_image_captions: bool = False
    skip_cache: bool = False
    max_pages: int | None = None
    page_range: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def to_form(self) -> dict[str, str]:
        form: dict[str, str] = {"output_format": self.output_format}
        if self.mode:
            form["mode"] = self.mode
        for name in (
            "paginate",
            "disable_image_extraction",
            "disable_image_captions",
            "skip_cache",
        ):
            if getattr(self, name):
                form[name] = "true"
        if self.page_range:
            form["page_range"] = self.page_range
        elif self.max_pages is not None:
            form["max_pages"] = str(self.max_pages)
        form.update(self.extra)
        return form


@dataclass
class ConvertResult:
    """Parsed response from GET /api/v1/convert/{request_id}."""

    status: str
    success: bool | None = None
    error: str | None = None
    markdown: str | None = None
    html: str | None = None
    json: dict[str, Any] | None = None
    images: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    page_count: int | None = None
    cost_cents: float | None = None
    result_url: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> ConvertResult:
        cost = (data.get("cost_breakdown") or {}).get("final_cost_cents")
        return cls(
            status=str(data.get("status") or "processing"),
            success=data.get("success"),
            error=data.get("error") or None,
            markdown=data.get("markdown"),
            html=data.get("html"),
            json=data.get("json"),
            images=data.get("images") or {},
            metadata=data.get("metadata") or {},
            page_count=data.get("page_count"),
            cost_cents=float(cost) if isinstance(cost, (int, float)) else None,
            result_url=data.get("result_url"),
        )

    def content_for(self, output_format: str) -> Any:
        return {"markdown": self.markdown, "html": self.html, "json": self.json}.get(output_format)
