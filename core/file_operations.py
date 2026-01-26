"""
FileOperations.py

Non-blocking parallel file operations using QThreadPool + QRunnable.
Each operation runs independently, enabling true parallelism.

Architecture:
    FileOperations (Controller)
        ├── copy()  ─→ CopyRunnable ──┐
        ├── move()  ─→ MoveRunnable ──┼─→ QThreadPool
        ├── trash() ─→ TrashRunnable ─┤
        └── rename()─→ RenameRunnable ┘
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from uuid import uuid4

from PySide6.QtCore import (
    QObject, Signal, Slot, QRunnable, QThreadPool, 
    QMutex, QMutexLocker, QThread, QMetaObject, Qt, Q_ARG
)

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


# =============================================================================
# JOB TRACKING
# =============================================================================
@dataclass
class FileJob:
    """Tracks a single file operation."""
    id: str
    op_type: str              # "copy", "move", "trash", "rename", "createFolder"
    source: str
    dest: str = ""
    transaction_id: str = ""  # Links this job to a larger transaction (batch)
    cancellable: Gio.Cancellable = field(default_factory=Gio.Cancellable)
    status: str = "pending"   # "pending", "running", "done", "cancelled", "error"
    skipped_files: List[str] = field(default_factory=list)


# =============================================================================
# SIGNAL HUB (Thread-safe signal emission)
# =============================================================================
class FileOperationSignals(QObject):
    """
    Signal hub for file operations.
    Runnables hold a reference and emit via QMetaObject.invokeMethod.
    """
    started = Signal(str, str, str)           # (job_id, op_type, path)
    progress = Signal(str, int, int)          # (job_id, current_bytes, total_bytes)
    # finished now includes transaction_id and dest/result path explicitly
    finished = Signal(str, str, str, str, bool, str)  # (tid, job_id, op_type, result_path, success, message)


# =============================================================================
# BASE RUNNABLE
# =============================================================================
class FileOperationRunnable(QRunnable):
    """Base class for file operation runnables."""
    
    def __init__(self, job: FileJob, signals: FileOperationSignals):
        super().__init__()
        self.job = job
        self.signals = signals
        self._last_progress_time = 0
        self.setAutoDelete(True)
    
    def emit_started(self):
        """Thread-safe signal emission."""
        self.job.status = "running"
        QMetaObject.invokeMethod(
            self.signals, "started",
            Qt.QueuedConnection,
            Q_ARG(str, self.job.id),
            Q_ARG(str, self.job.op_type),
            Q_ARG(str, self.job.source)
        )
    
    def emit_progress(self, current: int, total: int):
        """Throttled progress emission (10Hz max)."""
        now = time.time()
        if now - self._last_progress_time > 0.1 or current == total:
            self._last_progress_time = now
            QMetaObject.invokeMethod(
                self.signals, "progress",
                Qt.QueuedConnection,
                Q_ARG(str, self.job.id),
                Q_ARG(int, current),
                Q_ARG(int, total)
            )
    
    def emit_finished(self, success: bool, message: str):
        """Thread-safe completion signal."""
        self.job.status = "done" if success else "error"
        QMetaObject.invokeMethod(
            self.signals, "finished",
            Qt.QueuedConnection,
            Q_ARG(str, self.job.transaction_id),
            Q_ARG(str, self.job.id),
            Q_ARG(str, self.job.op_type),
            Q_ARG(str, self.job.dest if self.job.dest else self.job.source), # Result path (approx)
            Q_ARG(bool, success),
            Q_ARG(str, message)
        )
    
    def _progress_callback(self, current_bytes, total_bytes, user_data):
        """Gio progress callback adapter."""
        self.emit_progress(current_bytes, total_bytes)


# =============================================================================
# COPY RUNNABLE
# =============================================================================
class CopyRunnable(FileOperationRunnable):
    """Handles recursive file/directory copy with progress."""
    
    def run(self):
        self.emit_started()
        
        source = Gio.File.new_for_path(self.job.source)
        dest = Gio.File.new_for_path(self.job.dest)
        
        try:
            self.job.skipped_files = []
            self._recursive_copy(source, dest, self.job.cancellable)
            
            # Report result
            if self.job.skipped_files:
                count = len(self.job.skipped_files)
                print(f"[FILE_OPS:{self.job.id[:8]}] copy PARTIAL: {count} skipped")
                self.emit_finished(True, f"{self.job.dest}|PARTIAL:{count}")
            else:
                self.emit_finished(True, self.job.dest)
                
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.job.status = "cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else "error"
            print(f"[FILE_OPS:{self.job.id[:8]}] copy FAILED: {msg}")
            self.emit_finished(False, msg)
    
    def _recursive_copy(self, source, dest, cancellable):
        """Copy files/folders recursively."""
        info = source.query_info(
            "standard::type,standard::name",
            Gio.FileQueryInfoFlags.NONE,
            cancellable
        )
        file_type = info.get_file_type()
        
        if file_type == Gio.FileType.DIRECTORY:
            # Create destination directory
            try:
                dest.make_directory_with_parents(cancellable)
            except GLib.Error:
                pass  # May already exist
            
            # Enumerate children
            enumerator = None
            try:
                enumerator = source.enumerate_children(
                    "standard::name,standard::type",
                    Gio.FileQueryInfoFlags.NONE,
                    cancellable
                )
                
                for child_info in enumerator:
                    child_name = child_info.get_name()
                    child_source = source.get_child(child_name)
                    child_dest = dest.get_child(child_name)
                    
                    # Performance fix: Removed msleep(1)
                    try:
                        self._recursive_copy(child_source, child_dest, cancellable)
                    except GLib.Error as e:
                        if e.code == Gio.IOErrorEnum.CANCELLED:
                            raise
                        print(f"[FILE_OPS:{self.job.id[:8]}] SKIP: {child_name} - {e}")
                        self.job.skipped_files.append(child_source.get_path())
            finally:
                if enumerator:
                    enumerator.close(None)
        else:
            # Regular file copy
            try:
                source.copy(
                    dest,
                    Gio.FileCopyFlags.OVERWRITE,
                    cancellable,
                    self._progress_callback,
                    None
                )
            except GLib.Error as e:
                if e.code == Gio.IOErrorEnum.CANCELLED:
                    raise
                print(f"[FILE_OPS:{self.job.id[:8]}] SKIP: {source.get_path()} - {e}")
                self.job.skipped_files.append(source.get_path())


# =============================================================================
# MOVE RUNNABLE
# =============================================================================
class MoveRunnable(FileOperationRunnable):
    """Handles move with automatic directory merge fallback."""
    
    def run(self):
        self.emit_started()
        
        source = Gio.File.new_for_path(self.job.source)
        dest = Gio.File.new_for_path(self.job.dest)
        
        try:
            source.move(
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                self.job.cancellable,
                self._progress_callback,
                None
            )
            print(f"[FILE_OPS:{self.job.id[:8]}] move SUCCESS")
            self.emit_finished(True, self.job.dest)
            
        except GLib.Error as e:
            # Handle Directory Merge (WOULD_MERGE)
            if e.code == Gio.IOErrorEnum.WOULD_MERGE or e.code == 29:
                print(f"[FILE_OPS:{self.job.id[:8]}] WOULD_MERGE: recursive merge")
                try:
                    self.job.skipped_files = []
                    self._recursive_move_merge(source, dest, self.job.cancellable)
                    
                    if self.job.skipped_files:
                        count = len(self.job.skipped_files)
                        self.emit_finished(True, f"{self.job.dest}|PARTIAL:{count}")
                    else:
                        self.emit_finished(True, self.job.dest)
                except GLib.Error as merge_e:
                    msg = "Cancelled" if merge_e.code == Gio.IOErrorEnum.CANCELLED else str(merge_e)
                    self.emit_finished(False, msg)
            else:
                msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
                self.job.status = "cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else "error"
                print(f"[FILE_OPS:{self.job.id[:8]}] move FAILED: {msg}")
                self.emit_finished(False, msg)
    
    def _recursive_move_merge(self, source, dest, cancellable):
        """Move directory contents recursively (merge operation)."""
        enumerator = None
        try:
            enumerator = source.enumerate_children(
                "standard::name,standard::type",
                Gio.FileQueryInfoFlags.NONE,
                cancellable
            )
            
            for child_info in enumerator:
                child_name = child_info.get_name()
                child_source = source.get_child(child_name)
                child_dest = dest.get_child(child_name)
                
                child_type = child_info.get_file_type()
                dest_exists = child_dest.query_exists(cancellable)
                
                if child_type == Gio.FileType.DIRECTORY and dest_exists:
                    child_dest_info = child_dest.query_info(
                        "standard::type", Gio.FileQueryInfoFlags.NONE, cancellable
                    )
                    if child_dest_info.get_file_type() == Gio.FileType.DIRECTORY:
                        try:
                            self._recursive_move_merge(child_source, child_dest, cancellable)
                        except GLib.Error as e:
                            if e.code == Gio.IOErrorEnum.CANCELLED:
                                raise
                            self.job.skipped_files.append(child_source.get_path())
                        continue
                
                try:
                    child_source.move(
                        child_dest,
                        Gio.FileCopyFlags.OVERWRITE,
                        cancellable,
                        self._progress_callback,
                        None
                    )
                except GLib.Error as e:
                    if e.code == Gio.IOErrorEnum.CANCELLED:
                        raise
                    self.job.skipped_files.append(child_source.get_path())
        finally:
            if enumerator:
                enumerator.close(None)
            
        # Delete empty source folder
        source.delete(cancellable)


# =============================================================================
# NOTE: Trash operations are handled by TrashManager (core/trash_manager.py)
# FileOperations.trash() and restore_from_trash() delegate to TrashManager
# when available, or use a simple inline implementation as fallback.
# =============================================================================


class RenameRunnable(FileOperationRunnable):
    """Quick rename operation."""
    
    def run(self):
        self.emit_started()
        gfile = Gio.File.new_for_path(self.job.source)
        
        try:
            result = gfile.set_display_name(self.job.dest, self.job.cancellable)
            if result:
                new_path = result.get_path()
                self.emit_finished(True, new_path)
            else:
                self.emit_finished(False, "Rename failed")
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.emit_finished(False, msg)


# =============================================================================
# CREATE FOLDER RUNNABLE
# =============================================================================
class CreateFolderRunnable(FileOperationRunnable):
    """Quick folder creation."""
    
    def run(self):
        self.emit_started()
        gfile = Gio.File.new_for_path(self.job.source)
        
        try:
            gfile.make_directory(self.job.cancellable)
            self.emit_finished(True, "")
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.emit_finished(False, msg)



# =============================================================================
# INLINE TRASH RUNNABLE (Fallback)
# =============================================================================
class InlineTrashRunnable(FileOperationRunnable):
    """Fallback trash operation when TrashManager is unavailable."""
    
    def run(self):
        self.emit_started()
        gfile = Gio.File.new_for_path(self.job.source)
        
        try:
            gfile.trash(self.job.cancellable)
            self.emit_finished(True, self.job.source)
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.emit_finished(False, msg)


# =============================================================================
# CONTROLLER (Main thread interface)
# =============================================================================
class FileOperations(QObject):
    """
    Non-blocking parallel file operations controller.
    
    All operations run in QThreadPool, enabling true parallelism.
    Quick operations (trash, rename) don't block heavy ones (copy, move).
    
    Usage:
        file_ops = FileOperations()
        file_ops.operationCompleted.connect(on_done)
        job_id = file_ops.copy("/src/file.txt", "/dest/file.txt")
    """
    
    # Public signals (connect to these in UI)
    # Note: Signals now include job_id for tracking
    operationStarted = Signal(str, str, str)     # (job_id, op_type, path)
    operationProgress = Signal(str, int, int)    # (job_id, current, total)
    # Updated finished signal to include transaction ID
    operationFinished = Signal(str, str, str, str, bool, str)   # (tid, job_id, op_type, result_path, success, message)
    operationCompleted = Signal(str, str, str)   # (op_type, path, result) - LEGACY COMPAT for UI
    operationError = Signal(str, str, str)       # (op_type, path, error) - LEGACY COMPAT for UI

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Undo Manager reference
        self._undo_manager = None  # Injected via setUndoManager()
        self._trash_manager = None  # Injected via setTrashManager()
        # Thread pool (uses global instance for efficiency)
        self._pool = QThreadPool.globalInstance()
        
        # Active jobs tracking
        self._jobs: Dict[str, FileJob] = {}
        self._mutex = QMutex()
        
        # Signal hub for runnables
        self._signals = FileOperationSignals()
        self._signals.started.connect(self._on_started)
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
    
    def setUndoManager(self, undo_manager):
        """Inject an UndoManager to automatically record operations."""
        self._undo_manager = undo_manager
    
    def setTrashManager(self, trash_manager):
        """Inject a TrashManager to delegate trash operations."""
        if self._trash_manager:
            try:
                self._trash_manager.operationStarted.disconnect(self.operationStarted)
                self._trash_manager.operationProgress.disconnect(self.operationProgress)
                self._trash_manager.operationFinished.disconnect(self.operationFinished)
            except RuntimeError:
                pass

        self._trash_manager = trash_manager
        
        if self._trash_manager:
            # Proxy signals so TransactionManager only needs to listen to us
            self._trash_manager.operationStarted.connect(self.operationStarted)
            self._trash_manager.operationProgress.connect(self.operationProgress)
            self._trash_manager.operationFinished.connect(self.operationFinished)
    
    # -------------------------------------------------------------------------
    # INTERNAL SIGNAL HANDLERS
    # -------------------------------------------------------------------------
    def _on_started(self, job_id: str, op_type: str, path: str):
        """Forward started signal."""
        self.operationStarted.emit(job_id, op_type, path)
    
    def _on_progress(self, job_id: str, current: int, total: int):
        """Forward progress signal with job_id as path (for compat)."""
        # For overlay compatibility, emit with job_id
        self.operationProgress.emit(job_id, current, total)
    
    def _on_finished(self, tid: str, job_id: str, op_type: str, result_path: str, success: bool, message: str):
        """Handle completion and emit appropriate signal."""
        # Get job info
        with QMutexLocker(self._mutex):
            job = self._jobs.get(job_id)
            if job:
                del self._jobs[job_id]
        
        # Emit the new transaction-aware signal
        self.operationFinished.emit(tid, job_id, op_type, result_path, success, message)
        
        # Legacy signals for existing UI (ProgressOverlay)
        # We can eventually phase these out or have TransactionManager drive the UI.
        if success:
            self.operationCompleted.emit(op_type, result_path, message)
            
            # Undo Recording has been Moved to TransactionManager!
            # We no longer push to _undo_manager here.
            
        else:
            self.operationError.emit(op_type, result_path, message)
    
    # -------------------------------------------------------------------------
    # PUBLIC API (Non-blocking, returns job_id)
    # -------------------------------------------------------------------------
    @Slot(str, str, str, result=str)
    def copy(self, source_path: str, dest_path: str, transaction_id: str = "") -> str:
        """Copy a file/directory asynchronously. Returns job_id."""
        job = FileJob(
            id=str(uuid4()),
            op_type="copy",
            source=source_path,
            dest=dest_path,
            transaction_id=transaction_id
        )
        return self._submit(job, CopyRunnable)
    
    @Slot(str, str, str, result=str)
    def move(self, source_path: str, dest_path: str, transaction_id: str = "") -> str:
        """Move a file asynchronously. Returns job_id."""
        job = FileJob(
            id=str(uuid4()),
            op_type="move",
            source=source_path,
            dest=dest_path,
            transaction_id=transaction_id
        )
        return self._submit(job, MoveRunnable)
    
    @Slot(str, str, result=str)
    def trash(self, path: str, transaction_id: str = "") -> str:
        """
        Move a file to trash asynchronously. Returns job_id.
        Delegates to TrashManager if available.
        """
        if self._trash_manager:
            return self._trash_manager.trash(path, transaction_id)
        else:
            # Inline fallback using ThreadPool
            job = FileJob(
                id=str(uuid4()),
                op_type="trash",
                source=path,
                transaction_id=transaction_id
            )
            return self._submit(job, InlineTrashRunnable)
    
    @Slot(list)
    def trashMultiple(self, paths: list):
        """Trash multiple files (each as separate job)."""
        for path in paths:
            self.trash(path)
    
    @Slot(str, str, str, result=str)
    def rename(self, path: str, new_name: str, transaction_id: str = "") -> str:
        """Rename a file/folder asynchronously. Returns job_id."""
        job = FileJob(
            id=str(uuid4()),
            op_type="rename",
            source=path,
            dest=new_name,  # dest stores the new name
            transaction_id=transaction_id
        )
        return self._submit(job, RenameRunnable)
    
    @Slot(str, str, result=str)
    def createFolder(self, path: str, transaction_id: str = "") -> str:
        """Create a new folder asynchronously. Returns job_id."""
        job = FileJob(
            id=str(uuid4()),
            op_type="createFolder",
            source=path,
            transaction_id=transaction_id
        )
        return self._submit(job, CreateFolderRunnable)
    
    def _submit(self, job: FileJob, runnable_class) -> str:
        """Submit a job to the thread pool."""
        with QMutexLocker(self._mutex):
            self._jobs[job.id] = job
        
        runnable = runnable_class(job, self._signals)
        self._pool.start(runnable)
        return job.id

    @Slot(str, result=str)
    def restore_from_trash(self, original_path_to_restore: str) -> str:
        """
        Attempts to find a file in trash:/// that matches the given original path
        and restores it. Returns job_id.
        Delegates to TrashManager if available.
        """
        if self._trash_manager:
            return self._trash_manager.restore(original_path_to_restore)
        else:
            # No TrashManager available - cannot restore without it
            self.operationError.emit("restoreTrash", original_path_to_restore, "TrashManager not configured")
            return "no-trash-manager"
    
    # -------------------------------------------------------------------------
    # CANCELLATION
    # -------------------------------------------------------------------------
    @Slot(str)
    @Slot()
    def cancel(self, job_id: str = None):
        """
        Cancel operation(s).
        
        Args:
            job_id: Specific job to cancel, or None to cancel all.
        """
        with QMutexLocker(self._mutex):
            if job_id:
                job = self._jobs.get(job_id)
                if job:
                    job.cancellable.cancel()
                    job.status = "cancelled"
            else:
                # Cancel all
                for job in self._jobs.values():
                    job.cancellable.cancel()
                    job.status = "cancelled"
    
    def cancelAll(self):
        """Cancel all running operations."""
        self.cancel(None)
    
    # -------------------------------------------------------------------------
    # SYNCHRONOUS OPERATIONS (Quick, don't need threading)
    # -------------------------------------------------------------------------
    @Slot(str, result=bool)
    def openWithDefaultApp(self, path: str) -> bool:
        """Opens the file with its default application."""
        try:
            gfile = Gio.File.new_for_path(path)
            uri = gfile.get_uri()
            Gio.AppInfo.launch_default_for_uri(uri, None)
            return True
        except GLib.Error as e:
            self.operationError.emit("open", path, str(e))
            return False
    
    # -------------------------------------------------------------------------
    # STATUS QUERIES
    # -------------------------------------------------------------------------
    @Slot(result=int)
    def activeJobCount(self) -> int:
        """Returns number of currently running operations."""
        with QMutexLocker(self._mutex):
            return len(self._jobs)
    
    @Slot(str, result=str)
    def jobStatus(self, job_id: str) -> str:
        """Returns status of a specific job."""
        with QMutexLocker(self._mutex):
            job = self._jobs.get(job_id)
            return job.status if job else "unknown"
    
    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------
    def shutdown(self):
        """Cancel all operations and wait for completion."""
        self.cancelAll()
        self._pool.waitForDone(3000)  # Wait up to 3 seconds
