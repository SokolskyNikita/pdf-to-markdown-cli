#!/usr/bin/env python3
"""
Marker PDF to Markdown Converter

This script converts PDF files to markdown using the Marker API.
"""
import logging
import sys
import argparse

from docs_to_md.config.cli import create_config_from_args
from docs_to_md.core.processor import MarkerProcessor
from docs_to_md.utils.exceptions import ConfigurationError, DocsToMdError
from docs_to_md.utils.logging import setup_logging

# Setup logging
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        # We need a minimal parse to get verbosity before full config validation
        # Create a parser just for the verbose flag
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("-v", "--verbose", action="store_true")
        pre_args, _ = pre_parser.parse_known_args()
        
        # Setup logging based on verbosity
        log_level = logging.DEBUG if pre_args.verbose else logging.INFO
        setup_logging(level=log_level)

    except Exception as e:
        # Fallback logging setup if arg parsing fails early
        setup_logging() 
        logger.error(f"Failed during initial setup: {e}")
        return 3

    try:
        # Create full configuration from command-line arguments
        # This will re-parse but it's okay as argparse is idempotent
        config = create_config_from_args()
        
        # Create processor and run
        processor = MarkerProcessor(config)
        processor.process()
        
        logger.info("Conversion completed successfully.")
        return 0
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        return 1
        
    except DocsToMdError as e:
        logger.error(f"Processing error: {e}")
        return 2
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main()) 