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
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Create handlers
    handlers = []
    
    # Console handler (using stderr for better tqdm compatibility)
    console_handler = logging.StreamHandler(stream=sys.stderr) 
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers from root logger to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Add our handlers to root logger
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Silence noisy library loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("backoff").setLevel(logging.WARNING)

    # Get and return the application-specific logger
    logger = logging.getLogger("docs_to_md") # Updated name
    # Ensure the app logger also has the correct level if root is different
    logger.setLevel(level) 
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
        self.logger = logging.getLogger("docs_to_md.progress") # Updated name
        
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
        except Exception as e: # Catching generic Exception is broad, but okay for try/except on import/init
            self.logger.warning(f"Could not initialize tqdm: {e}. Falling back to log messages.")
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
            self.current += count
            # Log progress only periodically or based on some condition to avoid excessive logging
            if self.current % 10 == 0 or self.current == self.total: # Example: log every 10 updates or on completion
                 self.logger.info(f"{self.description}: {self.current}/{self.total}")
    
    def close(self) -> None:
        """Close the progress tracker and free resources."""
        if self._has_tqdm and self.pbar:
            self.pbar.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# Example usage (for testing):
# if __name__ == "__main__":
#     setup_logging()
#     log = logging.getLogger("docs_to_md")
#     log.info("Starting test")
#     with ProgressTracker(10, "Testing Progress") as pt:
#         for i in range(10):
#             time.sleep(0.2)
#             pt.update()
#     log.info("Finished test") 