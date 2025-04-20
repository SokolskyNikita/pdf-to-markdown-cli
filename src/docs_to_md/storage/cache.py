import logging
import threading
from typing import List, Optional
from pathlib import Path

from diskcache import Cache

from docs_to_md.storage.models import ConversionRequest
from docs_to_md.utils.exceptions import CacheError

logger = logging.getLogger(__name__)


class CacheManager:
    """Handles persistence of conversion requests."""

    def __init__(self, cache_dir: Path):
        """
        Initialize cache manager with given directory.
        
        Args:
            cache_dir: Directory for cache storage
            
        Raises:
            CacheError: If cache initialization fails
        """
        try:
            # Initialize with thread safety enabled
            self.cache: Cache = Cache(cache_dir, statistics=True, timeout=60)
            # Lock for thread-safe operations
            self._lock = threading.RLock()
        except Exception as e:
            logger.error(f"Failed to initialize cache in {cache_dir}: {e}")
            raise CacheError(f"Failed to initialize cache in {cache_dir}: {e}")

    def save(self, request: ConversionRequest) -> None:
        """
        Save request to cache.
        
        Args:
            request: Request to save
            
        Raises:
            CacheError: If save operation fails
        """
        with self._lock:
            try:
                self.cache.set(request.request_id, request.model_dump())
            except Exception as e:
                logger.error(f"Failed to save request {request.request_id}: {e}")
                raise CacheError(f"Failed to save request {request.request_id}: {e}")

    def get(self, request_id: str) -> Optional[ConversionRequest]:
        """
        Get request from cache.
        
        Args:
            request_id: ID of request to retrieve
            
        Returns:
            ConversionRequest if found, None otherwise
            
        Raises:
            CacheError: If retrieval fails
        """
        with self._lock:
            try:
                data = self.cache.get(request_id)
                if data:
                    return ConversionRequest.model_validate(data)
                return None
            except Exception as e:
                logger.error(f"Failed to get request {request_id}: {e}")
                return None

    def delete(self, request_id: str) -> bool:
        """
        Delete request from cache.
        
        Args:
            request_id: ID of request to delete
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                return bool(self.cache.delete(request_id))
            except Exception as e:
                logger.error(f"Failed to delete request {request_id}: {e}")
                return False

    def get_all(self) -> List[ConversionRequest]:
        """
        Get all requests from cache.
        
        Returns:
            List of all conversion requests
        """
        results = []
        # Use a consistent view of the cache to avoid inconsistencies 
        # during iteration
        with self._lock:
            keys = list(self.cache.iterkeys())
            
        for key in keys:
            if request := self.get(str(key)):
                results.append(request)
        return results

    def close(self) -> None:
        """Close cache connection and free resources."""
        with self._lock:
            try:
                self.cache.close()
            except Exception as e:
                logger.error(f"Error closing cache: {e}")
            
    def __enter__(self):
        """Support for context manager."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        self.close() 