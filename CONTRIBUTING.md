# Contributing

Thanks for helping improve `pdf-to-markdown-cli`. The most valuable contributions keep conversions reliable and predictable, and keep the CLI pleasant to script.

## Development setup

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git
cd pdf-to-markdown-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the checks CI runs:

```bash
pytest --cov
ruff check .
ruff format --check .
```

For manual testing against the live API, set a key and use the bundled samples. They are small, so they cost fractions of a cent:

```bash
export DATALAB_API_KEY="your_api_key"
pdf-to-md examples/alice_in_wonderland_sample.pdf -o /tmp/out --chunk-size 1 --paginate
```

## Project layout

```text
src/docs_to_md/
  cli.py         argument parsing, entry point, exit codes, run summary
  config.py      validated runtime configuration
  discovery.py   input discovery and deterministic output planning
  pipeline.py    splitting, concurrent submission, polling, per-file results
  client.py      Datalab Convert API client (retries, timeouts, error types)
  models.py      API request/response types and supported formats
  pdf.py         page-range parsing and PDF splitting (pikepdf)
  assemble.py    merging chunk outputs, image renaming, atomic writes
  markdown.py    Markdown line-break normalization
  console.py     terminal output, progress bar, logging setup
  errors.py      exception hierarchy
tests/           pytest suite; no test calls the live API
```

## Conventions

- Target Python 3.10+. Use type hints and `from __future__ import annotations`.
- Keep the stdout/stderr split: only converted file paths go to stdout.
- Raise exceptions from `errors.py`. Raise `FatalAPIError` only for problems that affect every request, such as a bad key or no credits.
- Keep CLI behavior backward-compatible unless a breaking change is intentional and documented in `CHANGELOG.md`.
- Never commit API keys, private documents, or build artifacts.

## Tests

Add or update tests whenever you change CLI options, output naming, discovery rules, API request/response handling, chunk merging, or error handling. Use `tests/conftest.py`'s `FakeClient` for pipeline tests, and a fake session (see `tests/test_client.py`) for HTTP behavior.

## Documentation

Update `README.md` for user-facing changes, `CHANGELOG.md` for anything release-visible, and `AGENTS.md` when the module map or conventions change.

`examples/` holds the sample PDFs used by the tests, next to their outputs from the current version. If output behavior changes, regenerate the outputs with `pdf-to-md examples --overwrite`. The Datalab API reference lives at <https://documentation.datalab.to/api-reference/>.

## Releasing

1. Bump `version` in `pyproject.toml` and move the `Unreleased` changelog notes under a `## [X.Y.Z] - YYYY-MM-DD` heading.
2. Commit, push `main`, and wait for CI to pass.
3. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The [release workflow](.github/workflows/release.yml) checks that the tag matches the package version, runs the tests, builds the sdist and wheel, and creates the GitHub release with those files attached and the changelog section as notes. It then publishes to PyPI through [Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

PyPI publishing needs a one-time setup. On pypi.org, go to the project's **Settings → Publishing** and add a GitHub publisher (`SokolskyNikita/pdf-to-markdown-cli`, workflow `release.yml`, environment `pypi`). Then set the repository variable `PYPI_PUBLISH=true`. Until then, upload manually with `twine upload dist/*`, using the files attached to the GitHub release.

## Reporting issues

Open a GitHub issue with the command you ran, the input file type, what you expected, and the output of the same command with `-v`.
