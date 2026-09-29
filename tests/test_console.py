import io
import logging
import subprocess
import sys

from docs_to_md import __version__
from docs_to_md.console import Console, setup_logging


class TtyStream(io.StringIO):
    def isatty(self):
        return True


def test_plain_output_when_not_a_tty():
    stderr = io.StringIO()
    console = Console(stdout=io.StringIO(), stderr=stderr)
    console.success("done")
    console.failure("broken")
    console.warning("careful")
    assert stderr.getvalue() == "✓ done\n✗ broken\nwarning: careful\n"


def test_color_on_tty_respects_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert Console(stderr=TtyStream()).color
    monkeypatch.setenv("NO_COLOR", "1")
    assert not Console(stderr=TtyStream()).color


def test_quiet_keeps_errors_only():
    stderr, stdout = io.StringIO(), io.StringIO()
    console = Console(quiet=True, stdout=stdout, stderr=stderr)
    console.info("hi")
    console.success("ok")
    console.skipped("skip")
    console.error("bad")
    console.result_path("/tmp/x.md")
    assert stderr.getvalue() == "error: bad\n"
    assert stdout.getvalue() == "/tmp/x.md\n"


def test_progress_bar_only_on_interactive_multi_chunk_runs():
    stderr = TtyStream()
    console = Console(stderr=stderr)
    console.start_progress(1, "Converting")
    assert console._bar is None
    console.start_progress(3, "Converting")
    assert console._bar is not None
    console.advance()
    console.info("message while bar is shown")
    console.stop_progress()
    assert console._bar is None
    assert "message while bar is shown" in stderr.getvalue()


def test_setup_logging_levels():
    setup_logging(verbose=True)
    assert logging.getLogger("docs_to_md").level == logging.DEBUG
    setup_logging(verbose=False)
    assert logging.getLogger("docs_to_md").level == logging.WARNING


def test_module_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "docs_to_md", "--version"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == f"pdf-to-md {__version__}"


def test_progress_counts_work_finished_before_the_bar_starts():
    console = Console(stderr=TtyStream())
    console.advance()
    console.start_progress(3, "Converting")
    assert console._bar.n == 1
    console.stop_progress()


def test_status_symbols_survive_legacy_encodings():
    raw = io.BytesIO()
    stderr = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
    Console(stderr=stderr).success("done → there")
    stderr.flush()
    assert raw.getvalue() == b"? done ? there\n"
