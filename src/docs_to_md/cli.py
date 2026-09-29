"""Command-line interface for pdf-to-md."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from docs_to_md import __version__
from docs_to_md.assemble import OUTPUT_EXTENSIONS
from docs_to_md.backends import BACKENDS, DEFAULT_BACKEND, get_backend
from docs_to_md.backends.mistral import MistralBackend
from docs_to_md.backends.openai import OpenAIBackend
from docs_to_md.config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT_SECONDS,
    Config,
)
from docs_to_md.console import Console, format_cost, format_elapsed, setup_logging
from docs_to_md.discovery import plan_jobs
from docs_to_md.errors import Cancelled, ConfigurationError, FatalAPIError
from docs_to_md.pipeline import CONVERTED, FAILED, SKIPPED, Pipeline

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

EPILOG = """\
examples:
  pdf-to-md report.pdf                  convert to report.md (+ report_images/)
  pdf-to-md docs/ -o out/               convert a folder tree into out/
  pdf-to-md scan.pdf --mode accurate    highest quality (slower, costs more)
  pdf-to-md book.pdf --page-range 0-9   first ten pages only (0-based)
  pdf-to-md *.docx --html --overwrite   re-convert, replacing existing outputs
  pdf-to-md scan.pdf --backend mistral  OCR with Mistral OCR instead
  pdf-to-md scan.pdf --backend openai   transcribe with GPT-Luna instead
  pdf-to-md scan.pdf --backend openrouter
                                        the same, through OpenRouter

Existing outputs are skipped unless --overwrite is given, so re-running a
command only converts what is missing. Converted file paths are printed to
stdout; progress and errors go to stderr.

environment:
  DATALAB_API_KEY    Datalab API key (MARKER_PDF_KEY is also accepted)
  MISTRAL_API_KEY    Mistral API key, for --backend mistral
  OPENAI_API_KEY     OpenAI API key, for --backend openai
  OPENROUTER_API_KEY OpenRouter API key, for --backend openrouter
  NO_COLOR           disable colored output

exit status:
  0 success, 1 one or more files failed, 2 usage or authentication error,
  130 interrupted
"""


def _key_value(text: str) -> tuple:
    key, sep, value = text.partition("=")
    if not sep or not key.strip():
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {text!r}")
    return key.strip(), value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-to-md",
        description=(
            "Convert PDFs, Office documents, ebooks, and images to Markdown, HTML,\n"
            "or JSON with the Datalab API, OCR them to Markdown with Mistral OCR,\n"
            "or transcribe PDFs and images with an OpenAI model (GPT-Luna),\n"
            "directly or through OpenRouter. Large PDFs are split into chunks that\n"
            "convert in parallel and are stitched back together."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, metavar="INPUT", help="files or directories to convert"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    out = parser.add_argument_group("output")
    fmt = out.add_mutually_exclusive_group()
    fmt.add_argument(
        "-f",
        "--format",
        dest="output_format",
        choices=tuple(OUTPUT_EXTENSIONS),
        default="markdown",
        help="output format (default: markdown)",
    )
    fmt.add_argument(
        "--html", dest="output_format", action="store_const", const="html", help="same as --format html"
    )
    fmt.add_argument(
        "--json", dest="output_format", action="store_const", const="json", help="same as --format json"
    )
    out.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        metavar="DIR",
        help="write outputs here, mirroring input folders (default: next to each input)",
    )
    out.add_argument(
        "--overwrite", action="store_true", help="replace existing outputs instead of skipping them"
    )
    out.add_argument(
        "--keep-line-breaks",
        dest="reflow_markdown",
        action="store_false",
        help="do not join hard-wrapped paragraph lines in Markdown output",
    )

    conv = parser.add_argument_group("conversion")
    conv.add_argument(
        "--backend",
        choices=tuple(BACKENDS),
        default=DEFAULT_BACKEND,
        help=f"conversion service (default: {DEFAULT_BACKEND})",
    )
    conv.add_argument(
        "-m",
        "--mode",
        choices=tuple(dict.fromkeys(mode for backend in BACKENDS.values() for mode in backend.info.modes)),
        help="quality/speed trade-off; Datalab defaults to fast, OpenAI and OpenRouter to balanced"
        " (Mistral has no modes)",
    )
    conv.add_argument(
        "--model",
        help="model for backends that offer a choice (defaults: "
        f"{MistralBackend.info.default_model} for Mistral, {OpenAIBackend.info.default_model} for OpenAI)",
    )
    conv.add_argument("--paginate", action="store_true", help="insert page separators in the output")
    conv.add_argument(
        "--no-images", dest="disable_image_extraction", action="store_true", help="do not extract images"
    )
    conv.add_argument(
        "--no-image-captions",
        dest="disable_image_captions",
        action="store_true",
        help="do not generate descriptions for images",
    )
    conv.add_argument(
        "--skip-cache", action="store_true", help="ignore Datalab's server-side result cache (Datalab only)"
    )
    conv.add_argument(
        "--api-option",
        dest="api_options",
        action="append",
        type=_key_value,
        default=[],
        metavar="KEY=VALUE",
        help="pass any other API field to the backend, e.g. service_tier=flex (repeatable)",
    )

    pages = parser.add_argument_group("pages and chunking")
    pages.add_argument("--page-range", metavar="RANGE", help="0-based pages to convert, e.g. '0,5-10'")
    pages.add_argument("--max-pages", type=int, metavar="N", help="convert at most N pages per document")
    chunk_defaults = ", ".join(f"{b.info.chunk_size} for {b.info.label}" for b in BACKENDS.values())
    pages.add_argument(
        "--chunk-size",
        type=int,
        metavar="N",
        help=f"PDF pages per API request (default: {chunk_defaults})",
    )
    pages.add_argument("--no-chunk", action="store_true", help="send each PDF as a single request")

    run = parser.add_argument_group("run control")
    run.add_argument("--api-key", metavar="KEY", help="API key (prefer the environment variables below)")
    run.add_argument(
        "-j",
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        metavar="N",
        help=f"requests in flight at once (default: {DEFAULT_CONCURRENCY})",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"give up on a request after this long (default: {DEFAULT_TIMEOUT_SECONDS:.0f})",
    )
    run.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would be converted without calling the API"
    )
    verbosity = run.add_mutually_exclusive_group()
    verbosity.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    verbosity.add_argument("-v", "--verbose", action="store_true", help="print debug logs")

    # Pre-1.0 spellings, kept working but hidden from --help.
    hidden = argparse.SUPPRESS
    parser.add_argument("-cs", dest="chunk_size", type=int, help=hidden)
    parser.add_argument("-mp", dest="max_pages", type=int, help=hidden)
    parser.add_argument("--pages", dest="paginate", action="store_true", help=hidden)
    parser.add_argument("--noimg", dest="disable_image_extraction", action="store_true", help=hidden)
    parser.add_argument("--llm", action="store_true", help=hidden)
    parser.add_argument("--max", action="store_true", help=hidden)
    parser.add_argument("--strip", action="store_true", help=hidden)
    parser.add_argument("--force", action="store_true", help=hidden)
    parser.add_argument("-l", "--langs", help=hidden)
    return parser


def resolve_api_key(explicit: str | None, env_vars: Sequence[str]) -> str | None:
    """``--api-key`` if given, else the first non-empty variable in ``env_vars``."""
    if explicit:
        return explicit.strip()
    for name in env_vars:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def config_from_args(args: argparse.Namespace, console: Console) -> Config:
    mode = args.mode
    if args.max or args.llm:
        legacy = "accurate" if args.max else "balanced"
        flag = "--max" if args.max else "--llm"
        if mode is None:
            mode = legacy
        console.warning(f"{flag} is deprecated; use --mode {legacy}")
    for flag, used in (("--strip", args.strip), ("--force", args.force), ("--langs", args.langs)):
        if used:
            console.warning(f"{flag} is no longer supported by the Datalab API and is ignored")

    backend = get_backend(args.backend)
    chunk_size = backend.info.chunk_size if args.chunk_size is None else args.chunk_size
    return Config(
        inputs=list(args.inputs),
        backend=backend.info.name,
        api_key=resolve_api_key(args.api_key, backend.info.api_key_env_vars),
        output_dir=args.output_dir,
        output_format=args.output_format,
        mode=mode,
        model=args.model,
        paginate=args.paginate,
        disable_image_extraction=args.disable_image_extraction,
        disable_image_captions=args.disable_image_captions,
        skip_cache=args.skip_cache,
        page_range=args.page_range,
        max_pages=args.max_pages,
        chunk_size=None if args.no_chunk else chunk_size,
        concurrency=args.concurrency,
        timeout=args.timeout,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        reflow_markdown=args.reflow_markdown,
        extra_options=dict(args.api_options),
    ).validate()


def _print_summary(console: Console, summary, dry_run: bool) -> None:
    converted, skipped, failed = (summary.count(s) for s in (CONVERTED, SKIPPED, FAILED))
    if dry_run:
        console.info(f"Dry run: {converted} to convert, {skipped} skipped, {failed} failed")
        return
    if len(summary.results) <= 1 and not skipped:
        return
    if not converted and not failed:
        console.info("Nothing to do: every output already exists (use --overwrite to redo)")
        return
    parts = [f"{converted} converted"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if failed:
        parts.append(f"{failed} failed")
    line = f"Done in {format_elapsed(summary.elapsed)}: {', '.join(parts)}"
    if summary.pages:
        line += f" · {summary.pages} pages"
    if summary.cost_cents:
        line += f" · {format_cost(summary.cost_cents)}"
    console.info(line)


def main(argv: Sequence[str] | None = None, console: Console | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    console = console or Console(quiet=args.quiet)

    stop_event = threading.Event()
    try:
        config = config_from_args(args, console)
        backend_type = get_backend(config.backend)
        jobs = plan_jobs(
            config.inputs,
            config.output_format,
            config.output_dir,
            input_extensions=backend_type.info.input_extensions,
        )
        if not jobs:
            console.error("No supported files to convert.")
            return EXIT_FAILURES
        backend = None if config.dry_run else backend_type.from_config(config, stop_event)
        pipeline = Pipeline(config, console, backend=backend, stop_event=stop_event)
        summary = pipeline.run(jobs)
    except ConfigurationError as e:
        console.error(str(e))
        return EXIT_USAGE
    except FatalAPIError as e:
        console.error(str(e))
        return EXIT_USAGE
    except (KeyboardInterrupt, Cancelled):
        stop_event.set()
        console.error("Interrupted.")
        return EXIT_INTERRUPTED

    _print_summary(console, summary, config.dry_run)
    return summary.exit_code


def entrypoint() -> None:
    code = main()
    if code in (EXIT_INTERRUPTED, EXIT_USAGE):
        # Don't wait for uploads still running in worker threads.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    sys.exit(code)
