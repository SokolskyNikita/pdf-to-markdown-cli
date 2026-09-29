"""Convert documents to Markdown, HTML, or JSON with the Datalab API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pdf-to-markdown-cli")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"
