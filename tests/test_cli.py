from __future__ import annotations

import dataclasses

import pytest

import docs_to_md.backends.datalab.backend as datalab_backend
import docs_to_md.cli as cli
from docs_to_md import __version__
from docs_to_md.backends import BACKENDS
from docs_to_md.backends.datalab.models import ConvertResult
from docs_to_md.config import Config
from docs_to_md.errors import ConfigurationError, FatalAPIError

from .conftest import CapturingConsole, FakeBackend, FakeClient


@pytest.fixture(autouse=True)
def no_ambient_key(monkeypatch):
    for backend in BACKENDS.values():
        for name in backend.info.api_key_env_vars:
            monkeypatch.delenv(name, raising=False)


def use_client(monkeypatch, client):
    """Make the Datalab backend talk to ``client`` instead of the real API."""
    monkeypatch.setattr(datalab_backend, "DatalabClient", lambda api_key, stop_event: client)
    return client


@pytest.fixture
def fake_client(monkeypatch):
    return use_client(monkeypatch, FakeClient())


def parse(*argv):
    console = CapturingConsole()
    args = cli.build_parser().parse_args(list(argv))
    return cli.config_from_args(args, console), console


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALAB_API_KEY", "env-key")
    config, console = parse(str(tmp_path))
    assert config.backend == "datalab"  # GPT-Luna only runs when asked for
    assert config.api_key == "env-key"
    assert config.output_format == "markdown"
    assert config.chunk_size == 25
    assert config.mode is None
    assert config.reflow_markdown is True
    assert config.normalize_superscripts is True and config.keep_partial is False
    assert console.err == ""


def test_api_key_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKER_PDF_KEY", "legacy")
    assert parse(str(tmp_path))[0].api_key == "legacy"
    monkeypatch.setenv("DATALAB_API_KEY", "new")
    assert parse(str(tmp_path))[0].api_key == "new"
    assert parse(str(tmp_path), "--api-key", "flag")[0].api_key == "flag"


def test_missing_api_key_is_a_usage_error(tmp_path):
    with pytest.raises(ConfigurationError, match="DATALAB_API_KEY"):
        parse(str(tmp_path))


def test_dry_run_does_not_need_a_key(tmp_path):
    config, _ = parse(str(tmp_path), "-n")
    assert config.dry_run and config.api_key is None


def test_format_options(tmp_path):
    assert parse(str(tmp_path), "-n", "--html")[0].output_format == "html"
    assert parse(str(tmp_path), "-n", "--json")[0].output_format == "json"
    assert parse(str(tmp_path), "-n", "-f", "html")[0].output_format == "html"
    with pytest.raises(SystemExit):
        parse(str(tmp_path), "--html", "--json")


def test_all_options(tmp_path):
    config, _ = parse(
        str(tmp_path),
        "-n",
        "-o",
        "out",
        "--overwrite",
        "--keep-line-breaks",
        "--keep-superscripts",
        "--keep-partial",
        "-m",
        "balanced",
        "--paginate",
        "--no-images",
        "--no-image-captions",
        "--skip-cache",
        "--api-option",
        "extras=extract_links",
        "--page-range",
        "0, 2-3",
        "--max-pages",
        "4",
        "--chunk-size",
        "10",
        "-j",
        "8",
        "--timeout",
        "60",
    )
    assert config.output_dir.is_absolute() and config.output_dir.name == "out"
    assert config.overwrite and not config.reflow_markdown
    assert not config.normalize_superscripts and config.keep_partial
    assert config.mode == "balanced"
    assert config.paginate and config.disable_image_extraction and config.disable_image_captions
    assert config.skip_cache
    assert config.extra_options == {"extras": "extract_links"}
    assert config.page_range == "0,2-3"
    assert (config.max_pages, config.chunk_size, config.concurrency, config.timeout) == (4, 10, 8, 60)


def test_no_chunk(tmp_path):
    assert parse(str(tmp_path), "-n", "--no-chunk")[0].chunk_size is None


def test_backend_option(tmp_path):
    assert parse(str(tmp_path), "-n", "--backend", "datalab")[0].backend == "datalab"
    with pytest.raises(SystemExit):
        parse(str(tmp_path), "-n", "--backend", "nope")


def test_llm_backends(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    config, _ = parse(str(tmp_path), "--backend", "openai")
    assert (config.backend, config.api_key, config.chunk_size, config.model) == (
        "openai",
        "sk-openai",
        1,
        None,
    )
    assert parse(str(tmp_path), "--backend", "openai", "--split-spreads")[0].split_spreads
    config, _ = parse(
        str(tmp_path), "--backend", "openrouter", "--model", "gpt-5.6-luna", "--chunk-size", "2"
    )
    assert (config.backend, config.api_key, config.chunk_size, config.model) == (
        "openrouter",
        "sk-or",
        2,
        "gpt-5.6-luna",
    )
    with pytest.raises(ConfigurationError, match="--chunk-size must be at least 1"):
        parse(str(tmp_path), "--backend", "openai", "--chunk-size", "0")
    with pytest.raises(ConfigurationError, match="does not take --model"):
        parse(str(tmp_path), "-n", "--model", "gpt-6-luna")


def test_mistral_backend(tmp_path, monkeypatch):
    with pytest.raises(ConfigurationError, match="MISTRAL_API_KEY"):
        parse(str(tmp_path), "--backend", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk")
    config, _ = parse(str(tmp_path), "--backend", "mistral", "--model", "mistral-ocr-2512")
    assert (config.backend, config.api_key, config.chunk_size, config.model) == (
        "mistral",
        "mk",
        25,
        "mistral-ocr-2512",
    )
    with pytest.raises(ConfigurationError, match="Mistral backend cannot produce json"):
        parse(str(tmp_path), "--backend", "mistral", "--json")


def test_llm_keys_do_not_change_the_default_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    with pytest.raises(ConfigurationError, match="DATALAB_API_KEY"):
        parse(str(tmp_path))
    monkeypatch.setenv("DATALAB_API_KEY", "dl")
    config, _ = parse(str(tmp_path))
    assert (config.backend, config.api_key, config.chunk_size, config.model) == ("datalab", "dl", 25, None)


def test_missing_llm_key_names_the_variable(tmp_path):
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        parse(str(tmp_path), "--backend", "openai")


def test_bad_api_option_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        parse(str(tmp_path), "--api-option", "novalue")


@pytest.mark.parametrize(("flag", "mode"), [("--llm", "balanced"), ("--max", "accurate")])
def test_deprecated_quality_flags_map_to_mode(tmp_path, flag, mode):
    config, console = parse(str(tmp_path), "-n", flag)
    assert config.mode == mode
    assert f"{flag} is deprecated; use --mode {mode}" in console.err


def test_explicit_mode_wins_over_deprecated_flag(tmp_path):
    assert parse(str(tmp_path), "-n", "--max", "-m", "fast")[0].mode == "fast"


@pytest.mark.parametrize("argv", [["--strip"], ["--force"], ["-l", "French"]])
def test_removed_api_flags_warn(tmp_path, argv):
    _, console = parse(str(tmp_path), "-n", *argv)
    assert "no longer supported" in console.err


def test_legacy_short_flags_still_work(tmp_path):
    config, _ = parse(str(tmp_path), "-n", "-cs", "5", "-mp", "2", "--pages", "--noimg")
    assert (config.chunk_size, config.max_pages) == (5, 2)
    assert config.paginate and config.disable_image_extraction


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--chunk-size", "0"], "chunk-size"),
        (["--max-pages", "0"], "max-pages"),
        (["-j", "0"], "concurrency"),
        (["--timeout", "0"], "timeout"),
        (["--page-range", "5-1"], "reversed"),
    ],
)
def test_invalid_values(tmp_path, argv, message):
    with pytest.raises(ConfigurationError, match=message):
        parse(str(tmp_path), "-n", *argv)


def test_output_dir_must_be_a_directory(tmp_path):
    file = tmp_path / "file"
    file.write_text("x")
    with pytest.raises(ConfigurationError, match="not a directory"):
        parse(str(tmp_path), "-n", "-o", str(file))


@pytest.fixture
def limited_backend(monkeypatch):
    """Register a keyless backend that only writes Markdown and has no modes."""

    class Limited(FakeBackend):
        info = dataclasses.replace(FakeBackend.info, name="limited", label="Limited")

    monkeypatch.setitem(BACKENDS, "limited", Limited)
    return Limited


def test_config_is_checked_against_the_backend(tmp_path, limited_backend):
    limited_backend.info = dataclasses.replace(limited_backend.info, output_formats=frozenset({"markdown"}))
    assert Config(inputs=[tmp_path], backend="limited").validate().api_key is None  # no key needed
    with pytest.raises(ConfigurationError, match="Limited backend cannot produce html"):
        Config(inputs=[tmp_path], backend="limited", output_format="html").validate()
    with pytest.raises(ConfigurationError, match="Unsupported mode for Limited: fast"):
        Config(inputs=[tmp_path], backend="limited", mode="fast").validate()
    with pytest.raises(ConfigurationError, match="Unknown backend"):
        Config(inputs=[tmp_path], backend="missing").validate()


def test_main_runs_any_registered_backend(examples, limited_backend):
    console = CapturingConsole()
    assert cli.main([str(examples), "--backend", "limited"], console=console) == cli.EXIT_OK
    assert (examples / "equations.md").read_text().startswith("# equations.pdf")
    assert "2 converted" in console.err


def test_config_rejects_unknown_values(tmp_path):
    with pytest.raises(ConfigurationError):
        Config(inputs=[tmp_path], api_key="k", output_format="docx").validate()
    with pytest.raises(ConfigurationError):
        Config(inputs=[tmp_path], api_key="k", mode="turbo").validate()
    with pytest.raises(ConfigurationError):
        Config(inputs=[], api_key="k").validate()


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"pdf-to-md {__version__}"


@pytest.mark.parametrize(
    ("argv", "total"),
    [
        ([], "$0.016"),  # Datalab fast: 4 pages at $4 per 1,000
        (["-m", "accurate"], "$0.040"),  # $10 per 1,000
        (["--backend", "mistral"], "$0.016"),
        (["--backend", "mistral", "--model", "mistral-ocr-2512"], "$0.008"),
        (["--backend", "openai"], "$0.003"),  # rough: 0.08 cents per page
        (["--backend", "openrouter", "--api-option", "service_tier=flex"], "$0.002"),
    ],
)
def test_dry_run_estimates_cost(examples, argv, total):
    console = CapturingConsole()
    assert cli.main([str(examples), "-n", *argv], console=console) == cli.EXIT_OK
    assert (
        f"Dry run: 2 to convert, 0 skipped, 0 failed · 4 pages · estimated {total} at list price"
        in console.err
    )


def test_dry_run_estimate_leaves_out_unknown_files(examples):
    (examples / "notes.docx").write_bytes(b"docx")
    console = CapturingConsole()
    assert cli.main([str(examples), "-n", "--model", "x", "--backend", "mistral"], console=console) == 0
    assert "estimated" not in console.err  # no price for model x
    console = CapturingConsole()
    assert cli.main([str(examples), "-n"], console=console) == 0
    assert "estimated $0.016 at list price (excluding 1 file)" in console.err


def test_main_converts_and_prints_paths(examples, fake_client, monkeypatch):
    monkeypatch.setenv("DATALAB_API_KEY", "k")
    console = CapturingConsole()
    assert cli.main([str(examples)], console=console) == cli.EXIT_OK
    assert console.out.splitlines() == [
        str(examples / "alice_in_wonderland_sample.md"),
        str(examples / "equations.md"),
    ]
    assert "Done in" in console.err and "2 converted" in console.err

    console = CapturingConsole()
    assert cli.main([str(examples)], console=console) == cli.EXIT_OK
    assert "Nothing to do" in console.err


def test_main_quiet_prints_only_paths(examples, fake_client, monkeypatch):
    monkeypatch.setenv("DATALAB_API_KEY", "k")
    console = CapturingConsole(quiet=True)
    assert cli.main([str(examples / "equations.pdf"), "-q"], console=console) == 0
    assert console.err == ""
    assert console.out.strip().endswith("equations.md")


def test_main_reports_failures_with_exit_code(examples, monkeypatch):
    use_client(monkeypatch, FakeClient(lambda *a: [ConvertResult(status="failed", error="nope")]))
    monkeypatch.setenv("DATALAB_API_KEY", "k")
    console = CapturingConsole()
    assert cli.main([str(examples)], console=console) == cli.EXIT_FAILURES
    assert "2 failed" in console.err


def test_main_usage_errors(tmp_path):
    console = CapturingConsole()
    assert cli.main([str(tmp_path / "missing.pdf"), "-n"], console=console) == cli.EXIT_USAGE
    assert "Input not found" in console.err
    assert cli.main([str(tmp_path)], console=console) == cli.EXIT_USAGE  # no API key


def test_main_no_files(tmp_path):
    console = CapturingConsole()
    assert cli.main([str(tmp_path), "-n"], console=console) == cli.EXIT_FAILURES
    assert "No supported files" in console.err


def test_main_fatal_api_error(examples, monkeypatch):
    class Failing(FakeClient):
        def submit(self, path, options):
            raise FatalAPIError("Authentication failed: bad key")

    use_client(monkeypatch, Failing())
    monkeypatch.setenv("DATALAB_API_KEY", "k")
    console = CapturingConsole()
    assert cli.main([str(examples)], console=console) == cli.EXIT_USAGE
    assert "Authentication failed" in console.err


def test_main_interrupted(examples, monkeypatch):
    class Interrupting(FakeClient):
        def submit(self, path, options):
            raise KeyboardInterrupt

    use_client(monkeypatch, Interrupting())
    monkeypatch.setenv("DATALAB_API_KEY", "k")
    console = CapturingConsole()
    assert cli.main([str(examples)], console=console) == cli.EXIT_INTERRUPTED
    assert "Interrupted" in console.err


def test_entrypoint_exits_with_main_code(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda: 1)
    with pytest.raises(SystemExit) as exc:
        cli.entrypoint()
    assert exc.value.code == 1


@pytest.mark.parametrize("code", [2, 130])
def test_entrypoint_hard_exits_when_workers_may_be_busy(monkeypatch, code):
    codes = []
    monkeypatch.setattr(cli, "main", lambda: code)
    monkeypatch.setattr(cli.os, "_exit", codes.append)
    with pytest.raises(SystemExit):  # the real os._exit never returns
        cli.entrypoint()
    assert codes == [code]
