"""FileOperations — Unified controller for all file I/O (Standard + Trash)."""

from uuid import uuid4
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QMutex, QMutexLocker, Qt

from core.file_workers import (
    FileJob, FileOperationSignals, _make_gfile, _gfile_path,
    TransferRunnable, RenameRunnable, CreateFolderRunnable,
    CreateFileRunnable, CreateSymlinkRunnable,
    generate_candidate_path,
)
from core.trash_workers import (
    TrashItem, SendToTrashRunnable, RestoreFromTrashRunnable,
    ListTrashRunnable, EmptyTrashRunnable
)

_MAX_RENAME_ATTEMPTS = 1000

def _split_name_ext(filename: str) -> tuple[str, str]:
    """Split filename into (base, ext). Handles .tar.gz and dotfiles."""
    if filename.endswith(".tar.gz"):
        return filename[:-7], ".tar.gz"
    dot = filename.rfind(".")
    if dot <= 0:
        return filename, ""
    return filename[:dot], filename[dot:]

class FileOperations(QObject):
    """Central controller for non-blocking file I/O via QThreadPool."""
    
    # Unified Signals
    operationStarted = Signal(str, str, str)     # (job_id, op_type, path)
    operationProgress = Signal(str, int, int)    # (job_id, current, total)
    operationFinished = Signal(str, str, str, str, bool, str)   # (tid, job_id, op_type, result_path, success, message)
    operationError = Signal(str, str, str, str, str, object)    # (tid, job_id, op_type, path, message, conflict_data)
    
    
    # Trash Specific Signals
    itemListed = Signal(object)             # TrashItem
    trashNotSupported = Signal(str, str)    # (path, error)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._undo_manager = None
        self._transaction_manager = None 
        self._pool = QThreadPool.globalInstance()
        self._jobs: Dict[str, FileJob] = {}
        self._mutex = QMutex()
        
        # Internal Signal Hub
        self._signals = FileOperationSignals()
        self._signals.started.connect(self._on_started)
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
        self._signals.operationError.connect(self._on_error)
        
        # Trash Specific Internal Signals
        self._signals.itemListed.connect(self.itemListed)
        self._signals.trashNotSupported.connect(self.trashNotSupported)
        
    def setUndoManager(self, undo_manager):
        self._undo_manager = undo_manager

    # -------------------------------------------------------------------------
    # SIGNAL HANDLERS
    # -------------------------------------------------------------------------
    def _on_started(self, job_id: str, op_type: str, path: str):
        self.operationStarted.emit(job_id, op_type, path)
    
    def _on_progress(self, job_id: str, current: int, total: int):
        self.operationProgress.emit(job_id, current, total)
    
    def _on_finished(self, tid: str, job_id: str, op_type: str, result_path: str, success: bool, message: str):
        with QMutexLocker(self._mutex):
            if job_id in self._jobs:
                del self._jobs[job_id]
        
        self.operationFinished.emit(tid, job_id, op_type, result_path, success, message)

    def _on_error(self, tid: str, job_id: str, op_type: str, path: str, message: str, conflict_data: object):
        self.operationError.emit(tid, job_id, op_type, path, message, conflict_data)

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    def setTransactionManager(self, tm):
        self._transaction_manager = tm

    def setUndoManager(self, undo_manager):
        self._undo_manager = undo_manager
    
    def _create_job(self, op_type: str, source: str, dest: str = "", tid: str = "", overwrite: bool = False, rename_to: str = "") -> FileJob:
        # [FIX] Generate ID first, then register with TransactionManager
        job_id = str(uuid4())
        
        if tid and self._transaction_manager:
            self._transaction_manager.addOperation(tid, op_type, source, dest, job_id)
            
        return FileJob(
            id=job_id,
            op_type=op_type,
            source=source,
            dest=dest,
            transaction_id=tid,
            overwrite=overwrite,
            rename_to=rename_to
        )

    def _submit(self, job: FileJob, runnable_class) -> str:
        with QMutexLocker(self._mutex):
            self._jobs[job.id] = job
        runnable = runnable_class(job, self._signals)
        self._pool.start(runnable)
        return job.id

    @Slot(str, str, str, bool, bool, result=str)
    def copy(self, source_path: str, dest_path: str, transaction_id: str = "", overwrite: bool = False, auto_rename: bool = False) -> str:
        job = self._create_job("copy", source_path, dest_path, transaction_id, overwrite)
        job.auto_rename = auto_rename
        return self._submit(job, TransferRunnable)
    
    @Slot(str, str, str, bool, result=str)
    def move(self, source_path: str, dest_path: str, transaction_id: str = "", overwrite: bool = False) -> str:
        job = self._create_job("move", source_path, dest_path, transaction_id, overwrite)
        return self._submit(job, TransferRunnable)
    
    @Slot(str, str, str, str, bool, bool, result=str)
    def transfer(self, source_path: str, dest_path: str, mode: str = "auto", transaction_id: str = "", overwrite: bool = False, auto_rename: bool = False) -> str:
        """
        Generic transfer method. 
        Mode: "copy", "move", or "auto" (guesses based on filesystem).
        """
        op_type = mode
        if mode == "auto":
            # Just default to move, the TransferRunnable will decide if cross-device
            op_type = "move"
            
        job = self._create_job(op_type, source_path, dest_path, transaction_id, overwrite)
        job.auto_rename = auto_rename
        return self._submit(job, TransferRunnable)

    @Slot(str, str, str, result=str)
    def rename(self, path: str, new_name: str, transaction_id: str = "") -> str:
        job = self._create_job("rename", path, new_name, transaction_id)
        return self._submit(job, RenameRunnable)
    
    @Slot(str, str, bool, result=str)
    def createFolder(self, path: str, transaction_id: str = "", auto_rename: bool = False) -> str:
        job = self._create_job("createFolder", path, "", transaction_id)
        job.auto_rename = auto_rename # Set manually as _create_job doesnt support it yet
        return self._submit(job, CreateFolderRunnable)

    @Slot(str, str, bool, result=str)
    def createFile(self, path: str, transaction_id: str = "", auto_rename: bool = False) -> str:
        """Create an empty file at the given path."""
        job = self._create_job("createFile", path, "", transaction_id)
        job.auto_rename = auto_rename
        return self._submit(job, CreateFileRunnable)

    @Slot(str, str, str, bool, result=str)
    def createSymlink(self, target: str, link_path: str, transaction_id: str = "", auto_rename: bool = False) -> str:
        """Create a symbolic link at link_path pointing to target."""
        job = self._create_job("createSymlink", target, link_path, transaction_id)
        job.auto_rename = auto_rename
        return self._submit(job, CreateSymlinkRunnable)

    # --- TRASH API ---

    @Slot(str, str, result=str)
    def trash(self, path: str, transaction_id: str = "") -> str:
        job = self._create_job("trash", path, "", transaction_id)
        return self._submit(job, SendToTrashRunnable)
    
    @Slot(list)
    def trashMultiple(self, paths: list):
        """Trash multiple files as a single batch transaction."""
        if not paths:
            return
        
        # Create a transaction for batch progress aggregation
        tid = ""
        if self._transaction_manager:
            tid = self._transaction_manager.startTransaction(f"Trashing {len(paths)} items")
        
        for path in paths:
            self.trash(path, transaction_id=tid)
            
        if tid and self._transaction_manager:
            self._transaction_manager.commitTransaction(tid)
            
    # Updated signature to match what TransactionManager needs
    @Slot(str, str, bool, str, result=str)
    def restore(self, original_path: str, transaction_id: str = "", overwrite: bool = False, rename_to: str = "") -> str:
        """Restores file from trash. Source is original path string."""
        job = self._create_job("restore", original_path, "", transaction_id, overwrite, rename_to)
        return self._submit(job, RestoreFromTrashRunnable)
        
    @Slot(str, result=str)
    def restore_from_trash(self, original_path_to_restore: str) -> str:
        """Alias for restore() for legacy compatibility."""
        return self.restore(original_path_to_restore)

    @Slot(result=str)
    def listTrash(self) -> str:
        job = self._create_job("list", "")
        return self._submit(job, ListTrashRunnable)
        
    @Slot(result=str)
    def emptyTrash(self) -> str:
        job = self._create_job("empty", "")
        return self._submit(job, EmptyTrashRunnable)

    # -------------------------------------------------------------------------
    # VFS HELPERS (delegates to Gio workers)
    # -------------------------------------------------------------------------

    def check_exists(self, path: str) -> bool:
        return _make_gfile(path).query_exists(None)

    def is_same_file(self, path_a: str, path_b: str) -> bool:
        return _make_gfile(path_a).equal(_make_gfile(path_b))

    def build_dest_path(self, src: str, dest_dir: str) -> str:
        """Build full dest path: dest_dir/basename(src)."""
        return _gfile_path(_make_gfile(dest_dir).get_child(_make_gfile(src).get_basename()))

    def build_renamed_dest(self, dest: str, new_name: str) -> str:
        """Replace filename in dest with new_name. Sanitizes to prevent path traversal."""
        if not new_name:
            return dest
        safe_name = _make_gfile(new_name).get_basename()
        if not safe_name:
            return dest
        parent = _make_gfile(dest).get_parent()
        if not parent:
            return dest
        return _gfile_path(parent.get_child(safe_name))

    def generate_unique_name(self, dest_path: str, style: str = "copy") -> str:
        """Find a conflict-free path by appending suffixes. Raises RuntimeError on limit."""
        for counter in range(1, _MAX_RENAME_ATTEMPTS + 1):
            candidate = generate_candidate_path(dest_path, counter, style=style)
            if not self.check_exists(candidate):
                return candidate
        raise RuntimeError(f"Auto-rename limit ({_MAX_RENAME_ATTEMPTS}) for: {dest_path}")

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------

    @Slot(str)
    @Slot()
    def cancel(self, job_id: str = None):
        with QMutexLocker(self._mutex):
            if job_id:
                job = self._jobs.get(job_id)
                if job:
                    job.cancellable.cancel()
                    job.status = "cancelled"
            else:
                for job in self._jobs.values():
                    job.cancellable.cancel()
                    job.status = "cancelled"

    def cancelAll(self):
        self.cancel(None)

    @Slot(result=int)
    def activeJobCount(self) -> int:
        with QMutexLocker(self._mutex):
            return len(self._jobs)

    @Slot(str, result=str)
    def jobStatus(self, job_id: str) -> str:
        with QMutexLocker(self._mutex):
            job = self._jobs.get(job_id)
            return job.status if job else "unknown"

    def shutdown(self):
        self.cancelAll()
        self._pool.waitForDone(3000)
