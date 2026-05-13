# Contributing

Thanks for contributing to `pdf-to-markdown-cli`.

## Development setup

1. Fork and clone the repository.
2. Create a virtual environment.
3. Install in editable mode:

```bash
pip install -e .
```

4. Run tests before submitting changes:

```bash
python -m unittest discover -s tests -v
```

## Pull request checklist

- Keep changes focused and explain the motivation.
- Add or update tests when behavior changes.
- Keep CLI behavior backward-compatible unless the change is intentional.
- Update docs (`README.md`, examples, or this guide) when user-facing behavior changes.
- Ensure all tests pass locally.

## Coding guidelines

- Target Python 3.10+.
- Prefer clear, small functions with explicit error handling.
- Avoid silent failures; log contextual errors where useful.
- Do not commit API keys, credentials, or private documents.

## Reporting issues

Use GitHub issues for bug reports and feature requests.
