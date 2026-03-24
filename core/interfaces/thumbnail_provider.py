"""
ThumbnailProviderBackend ABC - Contract for thumbnail generation.
"""

from abc import ABC, abstractmethod


class ThumbnailProviderBackend(ABC):
    """Contract for thumbnail generation."""

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """Check if this provider can generate thumbnails for the given MIME type."""
        pass

    @abstractmethod
    def generate(self, uri: str, mime_type: str, mtime: int) -> str | None:
        """
        Generate a thumbnail for the given URI.
        Returns path to thumbnail image or None on failure.
        """
        pass

    @abstractmethod
    def lookup(self, uri: str, mtime: int) -> str | None:
        """
        Look up an existing thumbnail.
        Returns path to thumbnail or None if not found.
        """
        pass
