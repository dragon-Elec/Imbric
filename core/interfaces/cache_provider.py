"""
CacheProvider ABC - Contract for mount-specific caching.
"""

from abc import ABC, abstractmethod
from typing import Optional


class CacheProvider(ABC):
    """Contract for caching layer."""

    @abstractmethod
    def get(self, key: str) -> Optional[object]:
        """Get cached value by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: object) -> None:
        """Set cached value."""
        pass

    @abstractmethod
    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache entry."""
        pass

    @abstractmethod
    def warm(self, path: str) -> None:
        """Pre-populate cache for a path (aggressive caching)."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached data."""
        pass
