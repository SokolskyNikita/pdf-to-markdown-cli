#!/usr/bin/env python3
"""Convert the benchmark samples with this checkout of pdf-to-md, then score the output.

Usage:
    python benchmarks/scanned_books/run.py --backend datalab --mode accurate
    python benchmarks/scanned_books/run.py --backend mistral --out benchmarks/scanned_books/baselines/mistral
    python benchmarks/scanned_books/run.py --backend openai -- --chunk-size 5

This calls the real API and costs money (about $0.12 for Datalab accurate, less
for the others). The API key comes from the usual environment variable. Output
goes to a temporary directory unless ``--out`` is given; arguments after ``--``
are passed to pdf-to-md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from score import score

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"


def convert(out: Path, backend: str, mode: str | None, extra: list[str]) -> int:
    command = [sys.executable, "-m", "docs_to_md", *sorted(map(str, (HERE / "samples").glob("*.pdf")))]
    command += ["--paginate", "--overwrite", "-o", str(out), "--backend", backend]
    command += ["--mode", mode] if mode else []
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(filter(None, [str(SRC), os.environ.get("PYTHONPATH")])),
    }
    return subprocess.run([*command, *extra], env=env, stdout=subprocess.DEVNULL, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backend", default="datalab")
    parser.add_argument("--mode")
    parser.add_argument("--out", type=Path, help="keep the output here")
    parser.add_argument("--json", action="store_true", help="print the scores as JSON")
    args, extra = parser.parse_known_args()
    extra = [a for a in extra if a != "--"]

    with tempfile.TemporaryDirectory(prefix="pdf-to-md-bench-") as tmp:
        out = args.out or Path(tmp)
        code = convert(out, args.backend, args.mode, extra)
        result = score(out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"accuracy {result['accuracy']:.2f}%", end="")
        for label, key in (("spelling", "probes"), ("order", "order")):
            print(f" · {label} {sum(result[key].values())}/{len(result[key])}", end="")
        found = sum(r["footnotes_found"] for r in result["samples"].values())
        expected = sum(r["footnotes_expected"] for r in result["samples"].values())
        print(f" · footnotes {found}/{expected}")
    return code


if __name__ == "__main__":
    sys.exit(main())
