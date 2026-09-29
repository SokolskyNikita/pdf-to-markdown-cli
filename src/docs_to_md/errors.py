class DocsToMdError(Exception):
    """Base exception for all application errors."""


class ConfigurationError(DocsToMdError):
    """Invalid command-line arguments or environment."""


class FileError(DocsToMdError):
    """A local file could not be read, written, or discovered."""


class PDFProcessingError(DocsToMdError):
    """A PDF could not be opened or split into chunks."""


class APIError(DocsToMdError):
    """The Datalab API returned an error for a single request."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RetryableAPIError(APIError):
    """A transient API failure (rate limit, server error, network issue)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message, status_code)
        self.retry_after = retry_after


class FatalAPIError(APIError):
    """An API failure that affects every request (bad key, no credits).

    Raising this aborts the whole run instead of failing a single file.
    """


class ResultProcessingError(DocsToMdError):
    """A completed API result could not be assembled or saved."""


class Cancelled(DocsToMdError):
    """Work was abandoned because the run was interrupted or aborted."""
