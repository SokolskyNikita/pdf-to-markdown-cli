# Contributing to pdf-to-md

Thanks for your interest in improving `pdf-to-md`! Bug reports, feature ideas, documentation fixes, and pull requests are all welcome.

## Ground rules

- **Reliability over features.** A conversion tool is only useful if you can trust it with a thousand files. Changes should keep runs predictable, re-runnable, and honest about failures.
- **Keep the CLI scriptable.** Only converted file paths go to stdout, and exit codes carry meaning. Don't print anything else to stdout.
- **Stay backward-compatible** unless a breaking change is deliberate. Document breaking changes in `CHANGELOG.md` and in the README's upgrade section.
- **Never commit** API keys, private documents, or build artifacts.

## Getting set up

```bash
git clone https://github.com/SokolskyNikita/pdf-to-markdown-cli.git
cd pdf-to-markdown-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

CI runs these on Linux, macOS, and Windows for every supported Python version. Run them before opening a pull request:

```bash
pytest --cov           # full offline suite; never calls the API
ruff check .           # lint
ruff format --check .  # formatting (`ruff format .` fixes it)
```

### Live API tests

`tests/test_live.py` converts every document in [`examples/`](examples/) with the real Datalab API. It checks text in nine languages and scripts, chunk merging, page numbering, images, and the HTML and JSON outputs. These tests are skipped by default. Run them when you change anything that affects conversion output:

```bash
DATALAB_API_KEY=... pytest -m live    # ~25 pages, a few cents
```

`tests/test_live_llm.py` runs the same samples through GPT-Luna, once through OpenAI and once through OpenRouter. Each route runs when its key is set:

```bash
OPENAI_API_KEY=... OPENROUTER_API_KEY=... \
  pytest -m live tests/test_live_llm.py
```

Maintainers can also run them from the **Live API tests** workflow in the Actions tab, which uses the repository's `DATALAB_API_KEY` secret, plus `OPENAI_API_KEY` and `OPENROUTER_API_KEY` if they're set.

## Project layout

```text
src/docs_to_md/
├── cli.py        arguments, entry point, exit codes, summary
├── config.py     validated runtime configuration
├── discovery.py  input discovery, deterministic output names
├── pipeline.py   split, convert chunks concurrently, report
├── backends/     conversion backends, selected with --backend
│   ├── base.py       Backend contract and BackendInfo capabilities
│   ├── datalab/      Datalab Convert API: submit/poll, HTTP client, types
│   └── openai/       GPT-Luna via OpenAI or OpenRouter: prompt, client
├── pdf.py        page ranges and PDF splitting (pikepdf)
├── assemble.py   merge chunks, renumber pages, write files
├── markdown.py   Markdown clean-up (reflow, captions)
├── console.py    terminal output, progress bar, logging
└── errors.py     exception hierarchy
tests/            pytest suite; samples.py lists examples/
examples/         sample documents with reference outputs
```

## Conventions

- Python 3.11+, type-hinted, with `from __future__ import annotations`.
- Raise exceptions from `errors.py`. Use `FatalAPIError` only for problems that affect every request (bad key, no credits). It aborts the whole run.
- Keep orchestration in `pipeline.py` and everything service-specific in its backend under `backends/`. The pipeline must not know which backend it runs. Pipeline tests use `FakeBackend` from `tests/conftest.py`. Datalab behavior is tested with `FakeClient` in `tests/test_datalab_backend.py`, and GPT-Luna with `FakeResponses` in `tests/test_openai_backend.py`. HTTP behavior is tested with the fake session from `conftest.py` in `tests/test_datalab_client.py` and `tests/test_openai_client.py`.
- A new backend subclasses `Backend` (`backends/base.py`), declares what it accepts in a `BackendInfo`, and is registered in `BACKENDS` (`backends/__init__.py`).
- Add tests with every behavior change, in the module's test file. The suite is fast (under a second), so keep it that way.
- Update the docs in the same pull request: `README.md` for user-facing changes, `CHANGELOG.md` under **Unreleased**, and `AGENTS.md` when the module map or conventions change.

## Reporting bugs and proposing features

Open an [issue](https://github.com/SokolskyNikita/pdf-to-markdown-cli/issues/new/choose) using the templates. For a bug, the most useful things are the exact command, the input type, and the output of the same command with `-v`. Please don't attach confidential documents.

## Releasing (maintainers)

1. Move the **Unreleased** changelog notes under a `## [X.Y.Z] - YYYY-MM-DD` heading and bump `version` in `pyproject.toml`.
2. Commit, push to `main`, and wait for CI to pass.
3. Tag and push: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.

The [release workflow](.github/workflows/release.yml) then:
- checks that the tag matches the package version, runs the tests, and builds the sdist and wheel;
- creates the GitHub release with both files attached and the changelog section as notes;
- publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), with no stored tokens.
