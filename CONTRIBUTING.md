# Contributing

Thanks for helping improve `pdf-to-markdown-cli`. This project is a Python CLI around the Datalab Marker API, so the most valuable contributions are changes that keep conversion behavior reliable, predictable, and easy to understand.

## Development setup

- Fork and clone the repository.
- Create and activate a virtual environment.
- Install the package in editable mode:

```bash
pip install -e .
```

- Run the test suite:

```bash
python -m unittest discover -s tests -v
```

For local CLI testing, set a Datalab API key:

```bash
export MARKER_PDF_KEY="your_api_key"
pdf-to-md ./examples/equations.pdf
```

## Project conventions

- Target Python 3.10+.
- Keep changes focused and explain the user-facing reason for the change.
- Prefer small functions, explicit state transitions, and contextual error messages.
- Keep CLI behavior backward-compatible unless the breaking change is intentional and documented.
- Use the existing exception hierarchy in `src/docs_to_md/utils/exceptions.py`.
- Use structured models and helpers that already exist before adding new abstractions.
- Do not commit API keys, credentials, private documents, or generated local cache/tmp data.

## Testing expectations

Run all tests before submitting:

```bash
python -m unittest discover -s tests -v
```

Add or update tests when you change:

- CLI parsing or config validation.
- Supported formats, MIME detection, or output extensions.
- Output path naming or image directory behavior.
- Cache/request state transitions.
- PDF chunking, polling, result assembly, or cleanup behavior.

The test suite does not call the live Datalab API. Use mocks for API behavior unless an explicit integration test setup is added.

## Documentation expectations

Update docs whenever user-facing behavior changes:

- `README.md` for installation, usage, options, supported formats, output behavior, and troubleshooting.
- `CHANGELOG.md` for release-visible changes.
- `AGENTS.md` for implementation maps and agent-facing project guidance.
- `CONTRIBUTING.md` for contributor workflow changes.

Treat `examples/*.md` as generated sample conversion outputs. Do not rewrite them as hand-authored docs unless the task is specifically to refresh examples.

`datalab_marker_api_docs.md` is copied Datalab API documentation for convenience. Avoid editing it as part of normal project documentation work.

## Pull request checklist

- The change has a clear motivation.
- Tests were added or updated when behavior changed.
- `python -m unittest discover -s tests -v` passes locally.
- User-facing docs were updated if needed.
- No credentials, private files, local caches, or build artifacts were committed.

## Reporting issues

Use GitHub issues for bug reports and feature requests. Include the command you ran, the file type you were converting, the expected result, and the error output or observed behavior.
