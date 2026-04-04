"""
IOBackend ABC - Contract for file I/O operations.
All file operations (copy, move, delete, create) go through this interface.
"""

from __future__ import annotations

from enum import StrEnum
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.file_job import FileJob, InversePayload


class BackendFeature(StrEnum):
    """Features that a backend might optionally support."""

    SYMLINK = "symlink"
    TRASH = "trash"
    HARDLINK = "hardlink"
    PERMISSIONS = "permissions"
    SEARCH = "search"


class IOBackend(ABC):
    """Contract for file I/O operations."""

    @abstractmethod
    def supports_feature(self, feature: BackendFeature) -> bool:
        """Query if the backend supports a specific feature."""
        pass

    @abstractmethod
    def set_signals(self, signals) -> None:
        """Inject the global FileOperationSignals hub into this backend."""
        pass

    @abstractmethod
    def build_inverse_payload(
        self, job: FileJob, result_path: str
    ) -> InversePayload | None:
        """Build reverse operation data for undo. Return None if not reversible."""
        pass

    @abstractmethod
    def copy(self, job: FileJob) -> str:
        """
        Copy a file or directory.
        Returns job_id.
        """
        pass

    @abstractmethod
    def move(self, job: FileJob) -> str:
        """
        Move a file or directory.
        Returns job_id.
        """
        pass

    @abstractmethod
    def batch_transfer(self, job: FileJob) -> str:
        """
        Execute a batch transfer of multiple items in a single thread.
        Returns job_id.
        """
        pass

    @abstractmethod
    def trash(self, job: FileJob) -> str:
        """
        Move a file to trash.
        Returns job_id.
        """
        pass

    @abstractmethod
    def restore(self, job: FileJob) -> str:
        """
        Restore a file from trash.
        Returns job_id.
        """
        pass

    @abstractmethod
    def delete(self, job: FileJob) -> str:
        """
        Permanently delete a file.
        Returns job_id.
        """
        pass

    @abstractmethod
    def create_folder(self, job: FileJob) -> str:
        """
        Create a folder.
        Returns job_id.
        """
        pass

    @abstractmethod
    def create_file(self, job: FileJob) -> str:
        """
        Create an empty file.
        Returns job_id.
        """
        pass

    @abstractmethod
    def rename(self, job: FileJob) -> str:
        """
        Rename a file.
        Returns job_id.
        """
        pass

    @abstractmethod
    def create_symlink(self, job: FileJob) -> str:
        """
        Create a symbolic link.
        Returns job_id.
        """
        pass

    @abstractmethod
    def list_trash(self, job: FileJob) -> str:
        """
        List items in the trash.
        Returns job_id. Result should be emitted via itemListed signal.
        """
        pass

    @abstractmethod
    def empty_trash(self, job: FileJob) -> str:
        """
        Permanently empty the trash.
        Returns job_id.
        """
        pass

    @abstractmethod
    def query_exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    def is_same_file(self, path_a: str, path_b: str) -> bool:
        """Check if two paths refer to the same file."""
        pass

    @abstractmethod
    def is_directory(self, path: str) -> bool:
        """Check if path is a directory."""
        pass

    @abstractmethod
    def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""
        pass

    @abstractmethod
    def is_regular_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        pass

    @abstractmethod
    def get_local_path(self, path: str) -> str | None:
        """
        Get the local POSIX path if available.
        Returns None for virtual backends (e.g. MTP) or if not supported.
        """
        pass
