import logging
import sys
from typing import Optional

# Keep tqdm import at top level
from tqdm import tqdm

def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up standardized logging configuration.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path to write logs to
        
    Returns:
        Logger instance for the application.
    """
    # Define base format
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Prepend logger name only for DEBUG level
    if level == logging.DEBUG:
        log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    # Create handlers
    handlers = []
    
    # Console handler (using stderr for better tqdm compatibility)
    console_handler = logging.StreamHandler(stream=sys.stderr) 
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except Exception as e:
            # Log error about file handler creation to stderr temporarily
            logging.basicConfig(level=logging.ERROR) # Basic config for this message
            logging.error(f"Failed to create log file handler for {log_file}: {e}", exc_info=False)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers from root logger to avoid duplication
    # This is important if setup_logging could be called multiple times
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Add our handlers to root logger
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Silence noisy library loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("backoff").setLevel(logging.WARNING)
    logging.getLogger("pikepdf").setLevel(logging.WARNING) # Added pikepdf

    # Get and return the application-specific logger
    # Ensures propagation is enabled by default
    logger = logging.getLogger("docs_to_md")
    logger.setLevel(level) # Ensure app logger level matches request
    return logger


class ProgressTracker:
    """
    Manages progress tracking for long-running operations.
    Uses tqdm for progress bars but abstracts its usage.
    """
    
    def __init__(self, total: int, description: str, unit: str = "item"):
        """
        Initialize a progress tracker.
        
        Args:
            total: Total number of items to process
            description: Description of the progress (shown in the bar)
            unit: Unit of items being processed
        """
        self.pbar: Optional[tqdm] = None
        self._has_tqdm: bool = False
        self.description = description # For fallback
        self.total = total # For fallback
        self.current = 0 # For fallback
        self.logger = logging.getLogger("docs_to_md.progress") # Consistent name
        
        # Check if stderr is a tty (interactive terminal) before trying tqdm
        # Avoids tqdm trying to initialize in non-interactive environments (like pipes)
        if sys.stderr.isatty():
            try:
                # Initialize tqdm here
                self.pbar = tqdm(
                    total=total, 
                    desc=description, 
                    unit=unit, 
                    file=sys.stderr, # Explicitly use stderr
                    leave=False
                    )
                self._has_tqdm = True
            except Exception as e:
                self.logger.warning(f"Could not initialize tqdm: {e}. Falling back to log messages.")
                self._has_tqdm = False
        else:
             self.logger.debug("Not initializing tqdm, stderr is not a TTY.")
             self._has_tqdm = False

    def __enter__(self):
        # The pbar is already created in __init__ if possible
        return self
    
    def update(self, count: int = 1) -> None:
        """
        Update progress count.
        
        Args:
            count: Number of items to add to progress (default: 1)
        """
        if self._has_tqdm and self.pbar:
            self.pbar.update(count)
        else:
            # Log progress using the dedicated logger if tqdm isn't active
            self.current += count
            # Log progress only periodically or based on some condition to avoid excessive logging
            # Log every 10% or the first/last update for less noise
            log_update = (self.current == 1 or
                          self.current == self.total or
                          (self.total > 0 and (self.current % max(1, self.total // 10)) == 0))

            if log_update and not self._has_tqdm: # Only log fallback if tqdm isn't running
                 self.logger.info(f"{self.description}: {self.current}/{self.total}")
    
    def close(self) -> None:
        """Close the progress tracker and free resources."""
        if self._has_tqdm and self.pbar:
            self.pbar.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()