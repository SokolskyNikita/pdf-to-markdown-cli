from pathlib import Path

import pytest

from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import ConfigurationError


def touch(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def names(jobs):
    return [(j.source.name, j.output.name, j.images_dir.name) for j in jobs]


def test_single_file_gets_deterministic_names(tmp_path):
    pdf = touch(tmp_path / "report.pdf")
    [job] = plan_jobs([pdf], "markdown")
    assert job.output == tmp_path / "report.md"
    assert job.images_dir == tmp_path / "report_images"
    assert job.is_pdf


def test_extension_follows_format(tmp_path):
    pdf = touch(tmp_path / "report.pdf")
    assert plan_jobs([pdf], "json")[0].output.name == "report.json"
    assert plan_jobs([pdf], "html")[0].output.name == "report.html"


def test_directory_is_walked_recursively_and_sorted(tmp_path):
    touch(tmp_path / "b.docx")
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "sub" / "c.png")
    touch(tmp_path / "notes.txt")
    jobs = plan_jobs([tmp_path], "markdown")
    assert [j.source.relative_to(tmp_path).as_posix() for j in jobs] == ["a.pdf", "b.docx", "sub/c.png"]


def test_hidden_files_and_directories_are_skipped(tmp_path):
    touch(tmp_path / ".hidden.pdf")
    touch(tmp_path / ".git" / "x.pdf")
    touch(tmp_path / "keep.pdf")
    assert names(plan_jobs([tmp_path], "markdown")) == [("keep.pdf", "keep.md", "keep_images")]


def test_generated_image_folders_are_not_reconverted(tmp_path):
    touch(tmp_path / "report.pdf")
    touch(tmp_path / "report.md")
    touch(tmp_path / "report_images" / "fig.png")
    # Pre-1.0 layout: <stem>_<key>.md next to images_<key>/
    touch(tmp_path / "old_1a2b3c4d.md")
    touch(tmp_path / "images_1a2b3c4d" / "fig.png")
    # A user folder that merely looks similar is still converted.
    touch(tmp_path / "images_2024" / "scan.png")
    jobs = plan_jobs([tmp_path], "markdown")
    assert [j.source.relative_to(tmp_path).as_posix() for j in jobs] == ["report.pdf", "images_2024/scan.png"]


def test_output_dir_mirrors_input_tree(tmp_path):
    src = tmp_path / "src"
    touch(src / "a.pdf")
    touch(src / "deep" / "b.pdf")
    out = tmp_path / "out"
    jobs = plan_jobs([src], "markdown", out)
    assert [j.output for j in jobs] == [out / "a.md", out / "deep" / "b.md"]


def test_output_dir_for_single_file(tmp_path):
    pdf = touch(tmp_path / "docs" / "a.pdf")
    [job] = plan_jobs([pdf], "markdown", tmp_path / "out")
    assert job.output == tmp_path / "out" / "a.md"


def test_same_stem_collisions_keep_source_extension(tmp_path):
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "a.docx")
    touch(tmp_path / "b.pdf")
    assert names(plan_jobs([tmp_path], "markdown")) == [
        ("a.docx", "a.docx.md", "a.docx_images"),
        ("a.pdf", "a.pdf.md", "a.pdf_images"),
        ("b.pdf", "b.md", "b_images"),
    ]


def test_never_overwrites_its_own_input(tmp_path):
    page = touch(tmp_path / "page.html")
    [job] = plan_jobs([page], "html")
    assert job.output == tmp_path / "page_converted.html"


def test_outputs_of_other_inputs_are_skipped(tmp_path):
    touch(tmp_path / "report.pdf")
    touch(tmp_path / "report.html")  # produced by a previous --html run...
    touch(tmp_path / "report_images" / "fig.png")  # ...as its images folder shows
    assert names(plan_jobs([tmp_path], "html")) == [("report.pdf", "report.html", "report_images")]


def test_user_file_that_looks_like_an_output_is_never_overwritten(tmp_path):
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "a.html", "<p>hand written</p>")
    jobs = plan_jobs([tmp_path], "html")
    assert {j.source.name: j.output.name for j in jobs} == {"a.html": "a.html.html", "a.pdf": "a.pdf.html"}
    # Those names are recognizably ours, so a re-run does not convert them.
    for job in jobs:
        touch(job.output)
    assert len(plan_jobs([tmp_path], "html")) == 2


def test_same_name_from_different_folders_with_output_dir(tmp_path):
    touch(tmp_path / "a" / "x.pdf")
    touch(tmp_path / "b" / "x.pdf")
    jobs = plan_jobs([tmp_path / "a" / "x.pdf", tmp_path / "b" / "x.pdf"], "markdown", tmp_path / "out")
    assert [j.output.name for j in jobs] == ["x.pdf.md", "x.pdf_2.md"]
    assert len({j.images_dir for j in jobs}) == 2


def test_names_differing_only_in_case_do_not_collide(tmp_path):
    touch(tmp_path / "Report.pdf")
    touch(tmp_path / "report.docx")
    outputs = [
        j.output.name for j in plan_jobs([tmp_path / "Report.pdf", tmp_path / "report.docx"], "markdown")
    ]
    assert len({o.casefold() for o in outputs}) == 2


def test_collision_outputs_from_a_previous_run_are_skipped(tmp_path):
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "a.docx")
    touch(tmp_path / "a.pdf.html")
    touch(tmp_path / "a.docx.html")
    assert [j.output.name for j in plan_jobs([tmp_path], "html")] == ["a.docx.html", "a.pdf.html"]


def test_directory_walk_lists_files_before_subfolders(tmp_path):
    touch(tmp_path / "z.pdf")
    touch(tmp_path / "a" / "b.pdf")
    assert [j.source.name for j in plan_jobs([tmp_path], "markdown")] == ["z.pdf", "b.pdf"]


def test_duplicate_inputs_are_deduplicated(tmp_path):
    pdf = touch(tmp_path / "a.pdf")
    assert len(plan_jobs([pdf, tmp_path, pdf], "markdown")) == 1


def test_missing_input(tmp_path):
    with pytest.raises(ConfigurationError, match="not found"):
        plan_jobs([tmp_path / "nope.pdf"], "markdown")


def test_unsupported_explicit_file(tmp_path):
    with pytest.raises(ConfigurationError, match="Unsupported file type"):
        plan_jobs([touch(tmp_path / "notes.txt")], "markdown")


def test_empty_directory_yields_no_jobs(tmp_path):
    assert plan_jobs([tmp_path], "markdown") == []
