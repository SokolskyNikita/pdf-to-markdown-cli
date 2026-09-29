"""User-facing terminal output: status lines, progress bar, and logging setup.

Converted file paths go to stdout (one per line) so the tool composes in
pipelines; everything else goes to stderr.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import TextIO

from tqdm import tqdm


def format_cost(cents: float) -> str:
    dollars = cents / 100
    return f"${dollars:.2f}" if dollars >= 0.01 or dollars == 0 else f"${dollars:.4f}"


def format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{seconds:.1f}s"


def setup_logging(verbose: bool) -> None:
    handler = logging.StreamHandler(sys.stderr)
    if verbose:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
    else:
        handler.setFormatter(logging.Formatter("warning: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.WARNING)
    logging.getLogger("docs_to_md").setLevel(logging.DEBUG if verbose else logging.WARNING)


def _supports_color(stream: TextIO) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


class Console:
    def __init__(self, quiet: bool = False, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr):
        self.quiet = quiet
        self.stdout = stdout
        self.stderr = stderr
        # Status symbols (✓, →) must not crash on legacy encodings, e.g. a
        # redirected stderr on Windows using cp1252.
        reconfigure = getattr(stderr, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
        self.color = _supports_color(stderr)
        self._bar: tqdm | None = None
        self._completed = 0
        self._lock = threading.Lock()

    def _style(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def _emit(self, message: str) -> None:
        with self._lock:
            if self._bar is not None:
                self._bar.write(message, file=self.stderr)
            else:
                print(message, file=self.stderr, flush=True)

    def info(self, message: str) -> None:
        if not self.quiet:
            self._emit(message)

    def success(self, message: str) -> None:
        if not self.quiet:
            self._emit(f"{self._style('✓', '32')} {message}")

    def skipped(self, message: str) -> None:
        if not self.quiet:
            self._emit(f"{self._style('-', '2')} {message}")

    def failure(self, message: str) -> None:
        self._emit(f"{self._style('✗', '31')} {message}")

    def error(self, message: str) -> None:
        self._emit(f"{self._style('error:', '1;31')} {message}")

    def warning(self, message: str) -> None:
        self._emit(f"{self._style('warning:', '33')} {message}")

    def result_path(self, path: str) -> None:
        with self._lock:
            print(path, file=self.stdout, flush=True)

    def start_progress(self, total: int, description: str) -> None:
        if self.quiet or not self.stderr.isatty() or total <= 1:
            return
        self._bar = tqdm(
            total=total,
            initial=min(self._completed, total),
            desc=description,
            unit="chunk",
            file=self.stderr,
            leave=False,
            dynamic_ncols=True,
        )

    def advance(self, count: int = 1) -> None:
        with self._lock:
            self._completed += count
            if self._bar is not None:
                self._bar.update(count)

    def stop_progress(self) -> None:
        with self._lock:
            if self._bar is not None:
                self._bar.close()
                self._bar = None
