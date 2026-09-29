from docs_to_md.models import (
    INPUT_MIME_TYPES,
    SUPPORTED_INPUT_EXTENSIONS,
    ConvertOptions,
    ConvertResult,
)


def test_default_form_only_sends_output_format():
    assert ConvertOptions().to_form() == {"output_format": "markdown"}


def test_form_serializes_flags_and_extras():
    form = ConvertOptions(
        output_format="html",
        mode="accurate",
        paginate=True,
        disable_image_extraction=True,
        disable_image_captions=True,
        skip_cache=True,
        max_pages=3,
        extra={"extras": "extract_links"},
    ).to_form()
    assert form == {
        "output_format": "html",
        "mode": "accurate",
        "paginate": "true",
        "disable_image_extraction": "true",
        "disable_image_captions": "true",
        "skip_cache": "true",
        "max_pages": "3",
        "extras": "extract_links",
    }


def test_page_range_takes_precedence_over_max_pages():
    form = ConvertOptions(page_range="0-2", max_pages=10).to_form()
    assert form["page_range"] == "0-2"
    assert "max_pages" not in form


def test_result_parses_current_api_field_names():
    result = ConvertResult.from_payload(
        {
            "status": "complete",
            "success": True,
            "error": "",
            "json": {"children": []},
            "html": "<p>x</p>",
            "images": None,
            "metadata": {"page_stats": []},
            "page_count": 2,
            "cost_breakdown": {"final_cost_cents": 0.6},
        }
    )
    assert result.json == {"children": []}
    assert result.content_for("html") == "<p>x</p>"
    assert result.content_for("json") == {"children": []}
    assert result.error is None
    assert result.images == {}
    assert result.cost_cents == 0.6


def test_every_extension_has_a_mime_type():
    assert set(INPUT_MIME_TYPES) == SUPPORTED_INPUT_EXTENSIONS
    assert {"pdf", "docx", "csv", "xlsm", "epub", "png"} <= SUPPORTED_INPUT_EXTENSIONS
