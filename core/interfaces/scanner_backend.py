"""
ScannerBackend ABC - Contract for directory scanning.
"""

from abc import ABC, abstractmethod


class ScannerBackend(ABC):
    """Contract for directory scanning."""

    @abstractmethod
    def scan_directory(self, path: str) -> None:
        """
        Start scanning a directory.
        Emits signals for file discovery.
        """
        pass

    @abstractmethod
    def scan_single_file(self, path: str) -> None:
        """
        Get info for a single file.
        Emits signal with FileInfo.
        """
        pass

    @abstractmethod
    def cancel(self) -> None:
        """Cancel ongoing scan operation."""
        pass
