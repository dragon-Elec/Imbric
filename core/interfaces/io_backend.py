"""
IOBackend ABC - Contract for file I/O operations.
All file operations (copy, move, delete, create) go through this interface.
"""

from __future__ import annotations

from enum import StrEnum
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypedDict, Any

if TYPE_CHECKING:
    from core.models.file_job import FileJob, InversePayload


class FileMetadata(TypedDict):
    """Standardized file metadata for backends."""

    size: int
    mtime: int  # Unix timestamp
    is_dir: bool
    is_symlink: bool


class BackendFeature(StrEnum):
    """Features that a backend might optionally support."""

    SYMLINK = "symlink"
    TRASH = "trash"
    HARDLINK = "hardlink"
    PERMISSIONS = "permissions"
    SEARCH = "search"


class BackendCapabilities(TypedDict):
    """Standardized report of backend physical and protocol constraints."""

    locality: str  # "local", "network", "virtual"
    latency_profile: str  # "low", "high"
    supports_preflight: bool  # Can scan many files efficiently
    supports_jit: bool  # Can pause/resume mid-operation
    reliable_mtime: bool  # Accurate timestamps
    reliable_size: bool  # Accurate file sizes
    fast_metadata_batching: bool  # Supports bulk children metadata fetch
    case_sensitive: bool


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
    def get_metadata(self, path: str) -> FileMetadata | None:
        """Query basic metadata for a path."""
        pass

    @abstractmethod
    def query_children_metadata(self, path: str) -> dict[str, FileMetadata]:
        """Query metadata for all children of a directory."""
        pass

    @abstractmethod
    def get_capabilities(self, path: str = "") -> BackendCapabilities:
        """Report backend capabilities (latency, locality, etc.) for a specific path."""
        pass

    def query_exists(self, path: str) -> bool:
        """Check if path exists."""
        return self.get_metadata(path) is not None

    @abstractmethod
    def is_same_file(self, path_a: str, path_b: str) -> bool:
        """Check if two paths refer to the same file."""
        pass

    def is_directory(self, path: str) -> bool:
        """Check if path is a directory."""
        meta = self.get_metadata(path)
        return meta["is_dir"] if meta else False

    def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""
        meta = self.get_metadata(path)
        return meta["is_symlink"] if meta else False

    def is_regular_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        meta = self.get_metadata(path)
        return (not meta["is_dir"] and not meta["is_symlink"]) if meta else False

    @abstractmethod
    def get_local_path(self, path: str) -> str | None:
        """
        Get the local POSIX path if available.
        Returns None for virtual backends (e.g. MTP) or if not supported.
        """
        pass

    @abstractmethod
    def resolve_conflict(
        self, job_id: str, action: str, new_dest: str = "", apply_to_all: bool = False
    ) -> bool:
        """
        Resolve a conflict encountered during JIT execution.
        Returns True if a paused job was found and resumed.
        """
        pass
