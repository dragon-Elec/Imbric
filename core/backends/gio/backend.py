"""
GIOBackend implementation of IOBackend and ScannerBackend interfaces.
Wraps the existing low-level GIO runnables and types.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from typing import Any, Dict, TYPE_CHECKING

from PySide6.QtCore import QThreadPool, QMutex, QMutexLocker

from core.interfaces.io_backend import (
    IOBackend,
    BackendFeature,
    FileMetadata,
    BackendCapabilities,
)
from core.interfaces.scanner_backend import ScannerBackend
from core.interfaces.metadata_provider import MetadataProvider
from core.models.file_job import FileJob
from core.models.file_info import FileInfo

if TYPE_CHECKING:
    from core.models.file_job import InversePayload

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
from core.backends.gio.helpers import _make_gfile, to_unix_timestamp


class GIOBackend(IOBackend):
    """GIO-based implementation of file operations."""

    def __init__(self):
        self._signals = None
        self._pool = QThreadPool.globalInstance()
        self._active_runnables: Dict[str, Any] = {}
        self._runnable_mutex = QMutex()

    def supports_feature(self, feature: BackendFeature) -> bool:
        # GIO is a very rich backend, it supports most features.
        # Hardware specific backends might not.
        return feature in {
            BackendFeature.SYMLINK,
            BackendFeature.TRASH,
            BackendFeature.HARDLINK,
            BackendFeature.PERMISSIONS,
            # Search might be supported separately or partially
            BackendFeature.SEARCH,
        }

    def set_signals(self, signals) -> None:
        self._signals = signals

    def build_inverse_payload(
        self, job: FileJob, result_path: str
    ) -> "InversePayload | None":
        """Return the inverse payload built by the runnable during execution."""
        return getattr(job, "inverse_payload", None)

    def _submit(self, job: FileJob, runnable_class) -> str:
        # Ensure a fresh cancellable for every job
        if not job.cancellable:
            job.cancellable = Gio.Cancellable()

        runnable = runnable_class(job, self._signals)

        with QMutexLocker(self._runnable_mutex):
            self._active_runnables[job.id] = runnable

        # Wrap the finished signal to clean up our tracking
        def cleanup():
            with QMutexLocker(self._runnable_mutex):
                self._active_runnables.pop(job.id, None)

        if hasattr(runnable, "finished"):  # Some runnables might have a finished signal
            runnable.finished.connect(cleanup)
        # Note: Since QThreadPool runnables don't have signals by default,
        # we'll need to handle cleanup in emit_finished in the runnable itself
        # for a more robust implementation. For now, we'll rely on resolve_conflict lookup.

        self._pool.start(runnable)
        return job.id

    def resolve_conflict(
        self, job_id: str, action: str, new_dest: str = "", apply_to_all: bool = False
    ) -> bool:
        """Resolve a conflict encountered during JIT execution."""
        with QMutexLocker(self._runnable_mutex):
            runnable = self._active_runnables.get(job_id)
            if runnable and hasattr(runnable, "resolve"):
                runnable.resolve(action, new_dest, apply_to_all)
                return True
            else:
                return False

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

    def get_metadata(self, path: str) -> FileMetadata | None:
        try:
            gfile = _make_gfile(path)
            info = gfile.query_info(
                "standard::size,standard::type,time::modified",
                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                None,
            )
            return self._info_to_metadata(info)
        except GLib.Error:
            return None

    def query_children_metadata(self, path: str) -> dict[str, FileMetadata]:
        try:
            gfile = _make_gfile(path)
            # Use bulk fetching for children attributes
            enumerator = gfile.enumerate_children(
                "standard::name,standard::size,standard::type,time::modified",
                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                None,
            )
            res = {}
            while True:
                info = enumerator.next_file(None)
                if not info:
                    break
                res[info.get_name()] = self._info_to_metadata(info)
            enumerator.close(None)
            return res
        except GLib.Error:
            return {}

    def get_capabilities(self, path: str = "") -> BackendCapabilities:
        # GIO handles both local and remote files. We check the path to determine capabilities.
        is_remote = False
        if path:
            if "://" in path:
                scheme = path.split("://")[0].lower()
                if scheme in {"smb", "mtp", "sftp", "ftp", "dav"}:
                    is_remote = True

        if is_remote:
            return {
                "locality": "remote",
                "latency_profile": "high",
                "supports_preflight": False,  # Remote metadata can be very slow
                "supports_jit": True,
                "reliable_mtime": False,  # MTP/SMB often drift or have lower precision
                "reliable_size": True,
                "fast_metadata_batching": False,
                "case_sensitive": True,  # Usually True for remote backends in GIO context
            }

        return {
            "locality": "local",
            "latency_profile": "low",
            "supports_preflight": True,
            "supports_jit": True,
            "reliable_mtime": True,
            "reliable_size": True,
            "fast_metadata_batching": True,
            "case_sensitive": True,
        }

    def _info_to_metadata(self, info: Gio.FileInfo) -> FileMetadata:
        """Helper to map GIO FileInfo to FileMetadata TypedDict."""
        return {
            "size": info.get_size(),
            "mtime": to_unix_timestamp(info.get_modification_date_time()),
            "is_dir": info.get_file_type() == Gio.FileType.DIRECTORY,
            "is_symlink": info.get_file_type() == Gio.FileType.SYMBOLIC_LINK,
        }

    def is_same_file(self, path_a: str, path_b: str) -> bool:
        return _make_gfile(path_a).equal(_make_gfile(path_b))

    def get_local_path(self, path: str) -> str | None:
        """Get the local POSIX path if available."""
        gfile = _make_gfile(path)
        return gfile.get_path()


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
