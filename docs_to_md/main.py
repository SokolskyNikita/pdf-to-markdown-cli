#!/usr/bin/env python3
"""
Marker PDF to Markdown Converter

This script converts PDF files to markdown using the Marker API.
"""
import logging
import os
import sys

from docs_to_md.config.cli import create_config_from_args
from docs_to_md.core.processor import MarkerProcessor
from docs_to_md.utils.exceptions import ConfigurationError, DocsToMdError
from docs_to_md.utils.logging import setup_logging

# Setup logging
logger = logging.getLogger(__name__)


def main() -> int:
    """
    Main entry point for the application.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Initialize logging configuration first
    setup_logging()
    
    try:
        # Create configuration from command-line arguments
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