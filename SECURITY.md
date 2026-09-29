# Security policy

## Supported versions

Security fixes are released for the latest version on [PyPI](https://pypi.org/project/pdf-to-markdown-cli/).

## Reporting a vulnerability

Please report vulnerabilities privately, not in public issues. Use GitHub's [private vulnerability reporting](https://github.com/SokolskyNikita/pdf-to-markdown-cli/security/advisories/new) for this repository. Include a description, steps to reproduce, and the affected version. You can expect an initial response within a week.

## What this tool sends where

- Documents are uploaded only to the Datalab API (`https://www.datalab.to/api/v1`), over HTTPS. Datalab deletes results about a day after conversion. See [Datalab's documentation](https://documentation.datalab.to/) for its data handling.
- The API key is sent only in the `X-API-Key` header to that endpoint. It is never written to disk or logs, not even with `-v`.
- Nothing is stored between runs. Temporary chunk files are deleted when a run ends.
