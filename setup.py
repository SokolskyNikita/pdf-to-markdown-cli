#!/usr/bin/env python3
"""Setup script for the pdf-to-markdown-cli package."""

from setuptools import setup, find_packages

# Read the contents of the README file for the long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Define runtime dependencies
# These are the packages required for the project to run.
# Version constraints are kept relatively flexible to avoid conflicts
# with other packages the user might have installed.
install_requires = [
    "backoff>=2.0",
    "diskcache>=5.0",
    "filetype>=1.0",
    "pikepdf>=8.0",
    "pydantic>=2.0",
    "ratelimit>=2.0",
    "requests>=2.0",
    "tqdm>=4.0",
]

setup(
    # Core package information
    name="pdf-to-markdown-cli",
    version="0.2.0",
    author="Nikita Sokolsky",
    description="CLI tool to convert PDF files (and other documents) to markdown using the Marker API.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/SokolskyNikita/pdf-to-markdown-cli",
    project_urls={
        "Bug Tracker": "https://github.com/SokolskyNikita/pdf-to-markdown-cli/issues",
    },
    keywords=["pdf", "markdown", "converter", "cli", "document", "marker", "md"],

    # Package discovery
    packages=find_packages(include=["docs_to_md", "docs_to_md.*"], exclude=["tests", "tests.*", "examples", "docs"]),

    # Metadata for PyPI
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Text Processing",
        "Topic :: Utilities",
    ],
    python_requires=">=3.10",

    # Dependencies
    install_requires=install_requires,

    # Entry points
    entry_points={
        "console_scripts": [
            "pdf-to-md=docs_to_md.main:main",
        ],
    },
) 