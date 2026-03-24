"""
MetadataProvider ABC - Contract for file metadata extraction.
"""

from abc import ABC, abstractmethod
from typing import Optional
from core.models.file_info import FileInfo


class MetadataProvider(ABC):
    """Contract for file metadata extraction."""

    @abstractmethod
    def get_file_info(
        self, path_or_uri: str, attributes: str = None
    ) -> Optional[FileInfo]:
        """
        Get metadata for a file.
        Returns FileInfo or None if file doesn't exist.
        """
        pass

    @abstractmethod
    def get_dimensions(self, path_or_uri: str) -> Optional[tuple[int, int]]:
        """
        Get image dimensions (width, height).
        Returns (width, height) or None if not an image/error.
        """
        pass

    @abstractmethod
    def get_item_count(self, path: str) -> int:
        """
        Get number of items in a directory.
        Returns count or -1 on error.
        """
        pass
