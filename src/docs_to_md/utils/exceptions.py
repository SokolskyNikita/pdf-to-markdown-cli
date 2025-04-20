class DocsToMdError(Exception):
    """Base exception for all docs-to-md errors."""
    pass


class ConfigurationError(DocsToMdError):
    """Error related to configuration loading or validation."""
    pass


class FileError(DocsToMdError):
    """Error related to file operations (reading, writing, discovery)."""
    pass


class APIError(DocsToMdError):
    """Error related to the external conversion API communication."""
    pass


class PDFProcessingError(DocsToMdError):
    """Error related to PDF manipulation (splitting, etc.)."""
    pass


class CacheError(DocsToMdError):
    """Error related to cache operations."""
    pass


class ResultProcessingError(DocsToMdError):
    """Error related to processing or combining results."""
    pass 