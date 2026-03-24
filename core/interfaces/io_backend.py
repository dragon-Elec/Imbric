"""
IOBackend ABC - Contract for file I/O operations.
All file operations (copy, move, delete, create) go through this interface.
"""

from abc import ABC, abstractmethod
from core.models.file_job import FileJob


class IOBackend(ABC):
    """Contract for file I/O operations."""

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
