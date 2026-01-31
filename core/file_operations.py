"""
[NEW] FileOperations (Controller)

Unified controller for all file operations (Standard + Trash).
Replaces the old split architecture (FileOperations vs TrashManager).
Uses shared worker classes for logic.
"""

from uuid import uuid4
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QMutex, QMutexLocker, Qt

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

# Import shared workers
from core.file_workers import (
    FileJob, FileOperationSignals,
    TransferRunnable, RenameRunnable, CreateFolderRunnable
)
from core.trash_workers import (
    TrashItem, SendToTrashRunnable, RestoreFromTrashRunnable,
    ListTrashRunnable, EmptyTrashRunnable
)

class FileOperations(QObject):
    """
    Central controller for Non-blocking file I/O.
    
    All operations run in QThreadPool.
    Handles Copy, Move, Rename, CreateFolder, Trash, Restore.
    SINGLE source of truth for TransactionManager.
    """
    
    # Unified Signals
    operationStarted = Signal(str, str, str)     # (job_id, op_type, path)
    operationProgress = Signal(str, int, int)    # (job_id, current, total)
    operationFinished = Signal(str, str, str, str, bool, str)   # (tid, job_id, op_type, result_path, success, message)
    operationError = Signal(str, str, str, str, str, object)    # (tid, job_id, op_type, path, message, conflict_data)
    
    # Legacy/UI Compatibility Signals
    operationCompleted = Signal(str, str, str)   # (op_type, path, result) 
    
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
        
        if success:
            self.operationCompleted.emit(op_type, result_path, message)

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
        # [FIX] Register intent with TransactionManager BEFORE execution
        if tid and self._transaction_manager:
            self._transaction_manager.addOperation(tid, op_type, source, dest)
            
        return FileJob(
            id=str(uuid4()),
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

    # --- TRASH API ---

    @Slot(str, str, result=str)
    def trash(self, path: str, transaction_id: str = "") -> str:
        job = self._create_job("trash", path, "", transaction_id)
        return self._submit(job, SendToTrashRunnable)
    
    @Slot(list)
    def trashMultiple(self, paths: list):
        for path in paths:
            self.trash(path)
            
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

    @Slot(str, result=bool)
    def openWithDefaultApp(self, path: str) -> bool:
        try:
            gfile = Gio.File.new_for_path(path)
            Gio.AppInfo.launch_default_for_uri(gfile.get_uri(), None)
            return True
        except GLib.Error as e:
            self.operationError.emit("", "open", "open", path, str(e), None)
            return False

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
