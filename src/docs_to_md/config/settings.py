from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

from docs_to_md.api.models import SUPPORTED_FORMAT_EXTENSIONS
from docs_to_md.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)
SETTINGS_DIR_NAME = ".docs_to_md"


@dataclass
class Config:
    """Global configuration for marker PDF conversion."""
    api_key: str
    
    input_path: str
    output_dir: Optional[Path] = None
    cache_dir: Path = Path.home() / SETTINGS_DIR_NAME / "cache" # Root directory for cache files
    root_tmp_dir: Path = Path.home() / SETTINGS_DIR_NAME / "tmp" # Root directory for temporary files
    
    output_format: str = "markdown"
    langs: str = "English"
    chunk_size: int = 25
    
    use_llm: bool = False
    strip_existing_ocr: bool = False
    disable_image_extraction: bool = False
    force_ocr: bool = False
    paginate: bool = False
    max_pages: Optional[int] = None
            
    def validate(self) -> None:
        if not self.api_key:
            raise ConfigurationError("API key is required")
                    
        if not self.input_path:
            raise ConfigurationError("Input path is required")
            
        if not Path(self.input_path).exists():
            raise ConfigurationError(f"Input path does not exist: {self.input_path}")
        
        if self.chunk_size < 1:
            raise ConfigurationError("Chunk size must be at least 1")
            
        if self.max_pages is not None and self.max_pages < 1:
            raise ConfigurationError("Max pages must be at least 1")
            
        if not self.output_format or self.output_format not in SUPPORTED_FORMAT_EXTENSIONS:
            raise ConfigurationError(f"Unsupported output format: {self.output_format}")
            
        if self.output_dir is not None and not self.output_dir.is_absolute():
            raise ConfigurationError(f"Output directory must be an absolute path: {self.output_dir}")