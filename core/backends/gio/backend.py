"""
GIOBackend implementation of IOBackend and ScannerBackend interfaces.
Wraps the existing low-level GIO runnables and types.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from PySide6.QtCore import QThreadPool

from core.interfaces.io_backend import IOBackend
from core.interfaces.scanner_backend import ScannerBackend
from core.interfaces.metadata_provider import MetadataProvider
from core.models.file_job import FileJob
from core.models.file_info import FileInfo

# Imports from GIO sub-package
from core.backends.gio.io_ops import (
    BatchTransferRunnable,
    TransferRunnable,
    RenameRunnable,
    CreateFolderRunnable,
    CreateFileRunnable,
    CreateSymlinkRunnable,
)
from core.backends.gio.trash_ops import (
    SendToTrashRunnable,
    RestoreFromTrashRunnable,
    ListTrashRunnable,
    EmptyTrashRunnable,
)
from core.backends.gio.scanner import FileScanner
from core.backends.gio.metadata import get_file_info
from core.backends.gio.helpers import _make_gfile


class GIOBackend(IOBackend):
    """GIO-based implementation of file operations."""

    def __init__(self):
        self._signals = None
        self._pool = QThreadPool.globalInstance()

    def set_signals(self, signals) -> None:
        self._signals = signals

    def _submit(self, job: FileJob, runnable_class) -> str:
        # Ensure a fresh cancellable for every job
        if not job.cancellable:
            job.cancellable = Gio.Cancellable()

        runnable = runnable_class(job, self._signals)
        self._pool.start(runnable)
        return job.id

    def copy(self, job: FileJob) -> str:
        return self._submit(job, TransferRunnable)

    def move(self, job: FileJob) -> str:
        return self._submit(job, TransferRunnable)

    def batch_transfer(self, job: FileJob) -> str:
        return self._submit(job, BatchTransferRunnable)

    def trash(self, job: FileJob) -> str:
        return self._submit(job, SendToTrashRunnable)

    def restore(self, job: FileJob) -> str:
        return self._submit(job, RestoreFromTrashRunnable)

    def list_trash(self, job: FileJob) -> str:
        return self._submit(job, ListTrashRunnable)

    def empty_trash(self, job: FileJob) -> str:
        return self._submit(job, EmptyTrashRunnable)

    def delete(self, job: FileJob) -> str:
        # GIO uses trash usually, but if we need direct delete:
        # Note: We might need a direct DeleteRunnable if requested
        # For now, trash is the primary GIO way
        return self.trash(job)

    def create_folder(self, job: FileJob) -> str:
        return self._submit(job, CreateFolderRunnable)

    def create_file(self, job: FileJob) -> str:
        return self._submit(job, CreateFileRunnable)

    def rename(self, job: FileJob) -> str:
        return self._submit(job, RenameRunnable)

    def create_symlink(self, job: FileJob) -> str:
        return self._submit(job, CreateSymlinkRunnable)

    def query_exists(self, path: str) -> bool:
        return _make_gfile(path).query_exists(None)

    def is_same_file(self, path_a: str, path_b: str) -> bool:
        return _make_gfile(path_a).equal(_make_gfile(path_b))


class GIOMetadataProvider(MetadataProvider):
    """GIO-based implementation of metadata extraction."""

    def get_file_info(
        self, path_or_uri: str, attributes: str | None = None
    ) -> FileInfo | None:
        return (
            get_file_info(path_or_uri, attributes=attributes)
            if attributes
            else get_file_info(path_or_uri)
        )

    def get_dimensions(self, path_or_uri: str) -> tuple[int, int] | None:
        # This is usually handled by DimensionWorker in Imbric,
        # but the interface expects a direct call.
        # For now, we return None and let the worker handle it via signals as per current design.
        return None

    def get_item_count(self, path: str) -> int:
        return -1  # Handled async by ItemCountWorker


# FileScanner already fulfills the ScannerBackend interface mostly,
# but we can wrap it if needed or just use it directly.
# For consistency with registry.py, we'll keep it as the scanner provider.
