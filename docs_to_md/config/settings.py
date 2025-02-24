from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import logging
import os

from docs_to_md.utils.exceptions import ConfigurationError
from docs_to_md.utils.file_utils import ensure_directory, get_env_var

logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Global configuration for marker PDF conversion."""
    # API settings
    api_key: str
    
    # Input/output settings
    input_path: str
    output_dir: Path = Path("converted")
    cache_dir: Path = Path(".docs_to_md_cache")
    tmp_dir: Path = Path("chunks")
    
    # Conversion settings
    output_format: str = "markdown"
    langs: str = "English"
    chunk_size: int = 25
    
    # Feature flags
    use_llm: bool = False
    strip_existing_ocr: bool = False
    disable_image_extraction: bool = False
    force_ocr: bool = False
    paginate: bool = False
    max_pages: Optional[int] = None
    
    @classmethod
    def from_env(cls, api_key_var: str = "MARKER_PDF_KEY") -> "Config":
        """
        Create a configuration from environment variables.
        
        Args:
            api_key_var: Environment variable name for API key
            
        Returns:
            Config instance with settings from environment
            
        Raises:
            ConfigurationError: If required environment variables are missing
        """
        try:
            api_key = get_env_var(api_key_var)
            
            # This will raise an error if MARKER_INPUT_PATH is not set
            input_path = get_env_var("MARKER_INPUT_PATH", required=False)
            
            if not input_path:
                raise ConfigurationError("No input path specified. Use MARKER_INPUT_PATH environment variable.")
                
            return cls(
                api_key=api_key,
                input_path=input_path,
                output_dir=Path(get_env_var("MARKER_OUTPUT_DIR", required=False) or "converted"),
                cache_dir=Path(get_env_var("DOCS_TO_MD_CACHE_DIR", required=False) or ".docs_to_md_cache"),
                output_format=get_env_var("MARKER_OUTPUT_FORMAT", required=False) or "markdown",
                langs=get_env_var("MARKER_LANGS", required=False) or "English",
                use_llm=get_env_var("MARKER_USE_LLM", required=False) == "1",
                chunk_size=int(get_env_var("MARKER_CHUNK_SIZE", required=False) or "25")
            )
        except ValueError as e:
            raise ConfigurationError(f"Invalid environment configuration: {e}")
            
    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        ensure_directory(self.output_dir)
        ensure_directory(self.cache_dir)
        ensure_directory(self.tmp_dir)
        
    def validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not self.api_key:
            raise ConfigurationError("API key is required")
            
        if not self.input_path:
            raise ConfigurationError("Input path is required")
            
        if self.chunk_size < 1:
            raise ConfigurationError("Chunk size must be at least 1")
            
        if self.max_pages is not None and self.max_pages < 1:
            raise ConfigurationError("Max pages must be at least 1")
            
        if self.output_format not in ["markdown", "json", "html", "txt"]:
            raise ConfigurationError(f"Unsupported output format: {self.output_format}")
            
        # Additional validations can be added here 

        if not self.output_dir.exists():
            try:
                ensure_directory(self.output_dir)
                logger.info(f"Created output directory: {self.output_dir}")
            except Exception as e:
                raise ConfigurationError(f"Failed to create output directory: {e}") 