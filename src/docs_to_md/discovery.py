"""Find input documents and decide where each conversion is written."""

from __future__ import annotations

import glob
import logging
import os
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from docs_to_md.assemble import OUTPUT_EXTENSIONS
from docs_to_md.errors import ConfigurationError

logger = logging.getLogger(__name__)

IMAGES_DIR_SUFFIX = "_images"
LEGACY_IMAGES_DIR_PREFIX = "images_"
_OUTPUT_EXTENSIONS = set(OUTPUT_EXTENSIONS.values())


@dataclass(frozen=True)
class Job:
    """One input document and the files its conversion produces."""

    source: Path
    output: Path
    images_dir: Path
    label: str  # short path for messages

    @property
    def is_pdf(self) -> bool:
        return self.source.suffix.lower() == ".pdf"


def is_supported(path: Path, input_extensions: Collection[str]) -> bool:
    return path.suffix.lower().lstrip(".") in input_extensions


def _is_generated_images_dir(path: Path) -> bool:
    """Is ``path`` an image folder this tool wrote next to an output file?

    Matches ``<stem>_images/`` beside ``<stem>.md`` and the pre-1.0 layout of
    ``images_<key>/`` beside ``<stem>_<key>.md``.
    """
    name = path.name
    if name.endswith(IMAGES_DIR_SUFFIX):
        stem = name[: -len(IMAGES_DIR_SUFFIX)]
        return any((path.parent / f"{stem}{ext}").exists() for ext in _OUTPUT_EXTENSIONS)
    if name.startswith(LEGACY_IMAGES_DIR_PREFIX):
        key = name[len(LEGACY_IMAGES_DIR_PREFIX) :]
        return bool(key) and any(
            any(path.parent.glob(f"*_{glob.escape(key)}{ext}")) for ext in _OUTPUT_EXTENSIONS
        )
    return False


def _walk(root: Path, input_extensions: Collection[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and not _is_generated_images_dir(current / d)
        )
        for name in sorted(filenames):
            path = current / name
            if not name.startswith(".") and is_supported(path, input_extensions):
                yield path


def discover(inputs: Iterable[Path], input_extensions: Collection[str]) -> list[tuple[Path, Path]]:
    """Return ``(source, root)`` pairs; ``root`` anchors the relative output path.

    Directories contribute only files whose extension is in ``input_extensions``;
    a file named explicitly with any other extension is an error.
    """
    found: list[tuple[Path, Path]] = []
    seen = set()
    for raw in inputs:
        path = raw.expanduser().resolve()
        if not path.exists():
            raise ConfigurationError(f"Input not found: {raw}")
        if path.is_dir():
            pairs = [(p, path) for p in _walk(path, input_extensions)]
            if not pairs:
                logger.warning("No supported files found in %s", raw)
        elif is_supported(path, input_extensions):
            pairs = [(path, path.parent)]
        else:
            raise ConfigurationError(
                f"Unsupported file type: {raw} (supported: {', '.join(sorted(input_extensions))})"
            )
        for source, root in pairs:
            if source not in seen:
                seen.add(source)
                found.append((source, root))
    return found


def display_path(path: Path) -> str:
    """``path`` relative to the working directory when possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def plan_jobs(
    inputs: Iterable[Path],
    output_format: str,
    output_dir: Path | None = None,
    *,
    input_extensions: Collection[str],
) -> list[Job]:
    """Discover inputs the backend accepts and assign each a deterministic output path.

    ``input_extensions`` comes from the backend's ``BackendInfo``.

    ``report.pdf`` becomes ``report.md`` with images in ``report_images/``. When
    two inputs would produce the same output (``a.pdf`` and ``a.docx``), both keep
    their source extension (``a.pdf.md``, ``a.docx.md``); remaining clashes (same
    file name in different folders flattened by ``-o``) get a ``_2``, ``_3`` suffix.
    Names are compared case-insensitively because macOS and Windows file systems
    are. A job's output never equals any input, so user files are never overwritten.

    Files recognizably written by an earlier run for another input are skipped, so
    re-running never converts its own results.
    """
    ext = OUTPUT_EXTENSIONS[output_format]
    sources = discover(inputs, input_extensions)

    def target_dir(source: Path, root: Path) -> Path:
        if output_dir is None:
            return source.parent
        return output_dir / source.parent.relative_to(root)

    def key(path: Path) -> str:
        return str(path).casefold()

    def is_generated_by(candidate: Path, source: Path, root: Path) -> bool:
        folder = target_dir(source, root)
        # Names only this tool produces are conclusive.
        if key(candidate) in {
            key(folder / f"{source.name}{ext}"),
            key(folder / f"{source.stem}_converted{ext}"),
        }:
            return True
        # A plain <stem><ext> could be a user's own file; require its images folder.
        return (
            key(candidate) == key(folder / f"{source.stem}{ext}")
            and (folder / f"{source.stem}{IMAGES_DIR_SUFFIX}").is_dir()
        )

    kept = []
    for source, root in sources:
        if any(s != source and is_generated_by(source, s, r) for s, r in sources):
            logger.debug("Skipping %s: it is the output of another input", source)
        else:
            kept.append((source, root))

    input_keys = {key(s) for s, _ in kept}
    stem_counts = Counter(key(target_dir(s, r) / s.stem) for s, r in kept)
    taken: set[str] = set()
    jobs: list[Job] = []
    for source, root in kept:
        folder = target_dir(source, root)
        stem = source.stem
        if stem_counts[key(folder / stem)] > 1 or key(folder / f"{stem}{ext}") in input_keys - {key(source)}:
            stem = source.name
        if key(folder / f"{stem}{ext}") == key(source):
            stem = f"{source.stem}_converted"
        base, counter = stem, 2
        while key(folder / f"{stem}{ext}") in taken or key(folder / f"{stem}{ext}") in input_keys:
            stem = f"{base}_{counter}"
            counter += 1
        taken.add(key(folder / f"{stem}{ext}"))
        jobs.append(
            Job(
                source=source,
                output=folder / f"{stem}{ext}",
                images_dir=folder / f"{stem}{IMAGES_DIR_SUFFIX}",
                label=display_path(source),
            )
        )
    return jobs
