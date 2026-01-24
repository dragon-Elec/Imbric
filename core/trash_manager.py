"""
[DONE] TrashManager — Native Freedesktop Trash Handling

Provides a robust, Nautilus-compatible trash implementation using Gio/GVFS.
Handles cross-partition trash, duplicates, and error cases gracefully.

Key Features:
- Uses `trash:///` virtual filesystem (aggregates all trash locations)
- Supports external drives (`.Trash-$UID` directories)
- Handles duplicates via `trash::deletion-date` sorting
- Graceful fallback when trashing is not supported
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QMutex, QMutexLocker

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


# =============================================================================
# DATA CLASSES
# =============================================================================
@dataclass
class TrashItem:
    """Represents an item in the trash."""
    trash_name: str          # Internal name in trash (e.g., "file.2.txt")
    display_name: str        # Original filename (e.g., "file.txt")
    original_path: str       # Where it came from (e.g., "/home/user/file.txt")
    deletion_date: str       # ISO format date string
    trash_uri: str           # Full URI (e.g., "trash:///file.2.txt")
    size: int = 0
    is_dir: bool = False


@dataclass
class TrashJob:
    """Represents a trash operation job."""
    id: str
    op_type: str             # "trash", "restore", "empty", "list"
    source: str = ""         # Original path (for trash/restore)
    cancellable: Gio.Cancellable = field(default_factory=Gio.Cancellable.new)
    status: str = "pending"


# =============================================================================
# SHARED SIGNALS (Thread-safe bridge)
# =============================================================================
class TrashSignals(QObject):
    """Signals emitted by trash operations."""
    started = Signal(str, str)              # (job_id, op_type)
    finished = Signal(str, str, bool, str)  # (job_id, op_type, success, message)
    progress = Signal(str, int, int)        # (job_id, current, total)
    itemListed = Signal(object)             # TrashItem (for list operation)
    trashNotSupported = Signal(str, str)    # (path, error_message) - for fallback prompt


# =============================================================================
# BASE RUNNABLE
# =============================================================================
class TrashRunnable(QRunnable):
    """Base class for trash operations."""
    
    def __init__(self, job: TrashJob, signals: TrashSignals):
        super().__init__()
        self.job = job
        self.signals = signals
        self.setAutoDelete(True)
    
    def emit_started(self):
        self.signals.started.emit(self.job.id, self.job.op_type)
    
    def emit_finished(self, success: bool, message: str = ""):
        self.job.status = "done" if success else "error"
        self.signals.finished.emit(self.job.id, self.job.op_type, success, message)


# =============================================================================
# TRASH (SEND TO TRASH)
# =============================================================================
class SendToTrashRunnable(TrashRunnable):
    """Moves a file to the trash."""
    
    def run(self):
        self.emit_started()
        path = self.job.source
        gfile = Gio.File.new_for_path(path)
        
        try:
            gfile.trash(self.job.cancellable)
            print(f"[TRASH:{self.job.id[:8]}] Trashed: {path}")
            self.emit_finished(True, path)
            
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.CANCELLED:
                self.emit_finished(False, "Cancelled")
            elif e.code == Gio.IOErrorEnum.NOT_SUPPORTED:
                # Cross-partition or unsupported filesystem
                # Signal the UI to offer permanent deletion
                print(f"[TRASH:{self.job.id[:8]}] NOT SUPPORTED: {path}")
                self.signals.trashNotSupported.emit(path, str(e))
                self.emit_finished(False, "Trash not supported on this drive")
            elif e.code == Gio.IOErrorEnum.PERMISSION_DENIED:
                print(f"[TRASH:{self.job.id[:8]}] PERMISSION DENIED: {path}")
                self.signals.trashNotSupported.emit(path, str(e))
                self.emit_finished(False, "Permission denied")
            else:
                print(f"[TRASH:{self.job.id[:8]}] FAILED: {e.message}")
                self.emit_finished(False, e.message)


# =============================================================================
# RESTORE (FROM TRASH)
# =============================================================================
class RestoreFromTrashRunnable(TrashRunnable):
    """Restores a file from trash to its original location."""
    
    def run(self):
        self.emit_started()
        original_path = self.job.source
        
        try:
            self._do_restore(original_path)
            print(f"[TRASH:{self.job.id[:8]}] Restored: {original_path}")
            self.emit_finished(True, original_path)
            
        except Exception as e:
            print(f"[TRASH:{self.job.id[:8]}] Restore FAILED: {e}")
            self.emit_finished(False, str(e))
    
    def _do_restore(self, original_path: str):
        """
        Scans trash:/// to find the most recently deleted item matching original_path.
        Then moves it back.
        """
        trash_root = Gio.File.new_for_uri("trash:///")
        
        # Enumerate trash to find our file
        enumerator = trash_root.enumerate_children(
            "standard::name,trash::orig-path,trash::deletion-date",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        candidate = None
        candidate_date = ""
        
        # Iterate all trash items
        while True:
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            
            orig_path = info.get_attribute_byte_string("trash::orig-path")
            if orig_path:
                # PyGObject might return str or bytes depending on version
                if isinstance(orig_path, bytes):
                    orig_path = orig_path.decode('utf-8', errors='ignore')
                
                if orig_path == original_path:
                    # Found a match! Check date to get the newest one if multiple
                    date = info.get_attribute_string("trash::deletion-date") or ""
                    
                    if candidate is None or date > candidate_date:
                        candidate = info
                        candidate_date = date
        
        enumerator.close(self.job.cancellable)
        
        if candidate:
            # We found the file in trash
            trash_name = candidate.get_name()
            trash_file = trash_root.get_child(trash_name)
            
            # Target is the original path
            dest_file = Gio.File.new_for_path(original_path)
            
            # Ensure parent directory exists (Nautilus does this)
            parent = dest_file.get_parent()
            if parent:
                try:
                    parent.make_directory_with_parents(self.job.cancellable)
                except GLib.Error:
                    pass  # Ignore exists error
            
            # Move it back (Restoration)
            trash_file.move(
                dest_file,
                Gio.FileCopyFlags.NONE,
                self.job.cancellable,
                None,
                None
            )
        else:
            raise Exception(f"File not found in trash: {original_path}")


# =============================================================================
# LIST TRASH
# =============================================================================
class ListTrashRunnable(TrashRunnable):
    """Lists all items in the trash."""
    
    def run(self):
        self.emit_started()
        
        try:
            items = self._list_trash()
            # Emit each item individually for progressive loading
            for item in items:
                self.signals.itemListed.emit(item)
            
            print(f"[TRASH:{self.job.id[:8]}] Listed {len(items)} items")
            self.emit_finished(True, str(len(items)))
            
        except Exception as e:
            print(f"[TRASH:{self.job.id[:8]}] List FAILED: {e}")
            self.emit_finished(False, str(e))
    
    def _list_trash(self) -> List[TrashItem]:
        """Enumerate all items in trash:///"""
        trash_root = Gio.File.new_for_uri("trash:///")
        items = []
        
        enumerator = trash_root.enumerate_children(
            "standard::name,standard::display-name,standard::size,standard::type,"
            "trash::orig-path,trash::deletion-date",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        while True:
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            
            trash_name = info.get_name()
            display_name = info.get_display_name()
            size = info.get_size()
            is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
            
            orig_path = info.get_attribute_byte_string("trash::orig-path") or ""
            if isinstance(orig_path, bytes):
                orig_path = orig_path.decode('utf-8', errors='ignore')
            
            date = info.get_attribute_string("trash::deletion-date") or ""
            
            items.append(TrashItem(
                trash_name=trash_name,
                display_name=display_name,
                original_path=orig_path,
                deletion_date=date,
                trash_uri=f"trash:///{trash_name}",
                size=size,
                is_dir=is_dir
            ))
        
        enumerator.close(self.job.cancellable)
        
        # Sort by deletion date (newest first)
        items.sort(key=lambda x: x.deletion_date, reverse=True)
        return items


# =============================================================================
# EMPTY TRASH
# =============================================================================
class EmptyTrashRunnable(TrashRunnable):
    """Permanently deletes all items in the trash."""
    
    def run(self):
        self.emit_started()
        
        try:
            deleted_count = self._empty_trash()
            print(f"[TRASH:{self.job.id[:8]}] Emptied {deleted_count} items")
            self.emit_finished(True, str(deleted_count))
            
        except Exception as e:
            print(f"[TRASH:{self.job.id[:8]}] Empty FAILED: {e}")
            self.emit_finished(False, str(e))
    
    def _empty_trash(self) -> int:
        """Delete all items in trash:///"""
        trash_root = Gio.File.new_for_uri("trash:///")
        deleted = 0
        
        enumerator = trash_root.enumerate_children(
            "standard::name",
            Gio.FileQueryInfoFlags.NONE,
            self.job.cancellable
        )
        
        while True:
            if self.job.cancellable.is_cancelled():
                break
                
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            
            trash_name = info.get_name()
            trash_file = trash_root.get_child(trash_name)
            
            try:
                # Use delete with recursive=True for directories
                trash_file.delete(self.job.cancellable)
                deleted += 1
                self.signals.progress.emit(self.job.id, deleted, -1)  # Total unknown
            except GLib.Error as e:
                # Try recursive delete for non-empty directories
                if e.code == Gio.IOErrorEnum.NOT_EMPTY:
                    self._delete_recursive(trash_file)
                    deleted += 1
                else:
                    print(f"[TRASH] Failed to delete {trash_name}: {e.message}")
        
        enumerator.close(self.job.cancellable)
        return deleted
    
    def _delete_recursive(self, gfile: Gio.File):
        """Recursively delete a directory."""
        enumerator = gfile.enumerate_children(
            "standard::name,standard::type",
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            self.job.cancellable
        )
        
        while True:
            info = enumerator.next_file(self.job.cancellable)
            if not info:
                break
            
            child = gfile.get_child(info.get_name())
            if info.get_file_type() == Gio.FileType.DIRECTORY:
                self._delete_recursive(child)
            else:
                child.delete(self.job.cancellable)
        
        enumerator.close(self.job.cancellable)
        gfile.delete(self.job.cancellable)


# =============================================================================
# TRASH MANAGER (Main Thread Interface)
# =============================================================================
class TrashManager(QObject):
    """
    Non-blocking trash operations manager.
    
    All operations run in QThreadPool for parallelism.
    Provides native freedesktop.org trash compliance.
    
    Usage:
        trash_mgr = TrashManager()
        trash_mgr.operationFinished.connect(on_done)
        trash_mgr.trashNotSupported.connect(on_fallback_needed)
        trash_mgr.trash("/path/to/file.txt")
    """
    
    # Public signals
    operationStarted = Signal(str, str)              # (job_id, op_type)
    operationFinished = Signal(str, str, bool, str)  # (job_id, op_type, success, message)
    operationProgress = Signal(str, int, int)        # (job_id, current, total)
    itemListed = Signal(object)                      # TrashItem
    trashNotSupported = Signal(str, str)             # (path, error) - for "Delete permanently?" dialog
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._mutex = QMutex()
        self._jobs = {}
        
        # Internal signals bridge
        self._signals = TrashSignals()
        self._signals.started.connect(self._on_started)
        self._signals.finished.connect(self._on_finished)
        self._signals.progress.connect(self.operationProgress)
        self._signals.itemListed.connect(self.itemListed)
        self._signals.trashNotSupported.connect(self.trashNotSupported)
    
    # -------------------------------------------------------------------------
    # PRIVATE SLOTS
    # -------------------------------------------------------------------------
    def _on_started(self, job_id: str, op_type: str):
        self.operationStarted.emit(job_id, op_type)
    
    def _on_finished(self, job_id: str, op_type: str, success: bool, message: str):
        with QMutexLocker(self._mutex):
            if job_id in self._jobs:
                del self._jobs[job_id]
        self.operationFinished.emit(job_id, op_type, success, message)
    
    def _submit(self, job: TrashJob, runnable_class) -> str:
        """Submit a job to the thread pool."""
        with QMutexLocker(self._mutex):
            self._jobs[job.id] = job
        
        runnable = runnable_class(job, self._signals)
        self._pool.start(runnable)
        return job.id
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    @Slot(str, result=str)
    def trash(self, path: str) -> str:
        """Move a file to trash. Returns job_id."""
        job = TrashJob(
            id=str(uuid4()),
            op_type="trash",
            source=path
        )
        return self._submit(job, SendToTrashRunnable)
    
    @Slot(list)
    def trashMultiple(self, paths: list):
        """Trash multiple files (each as separate job)."""
        for path in paths:
            self.trash(path)
    
    @Slot(str, result=str)
    def restore(self, original_path: str) -> str:
        """Restore a file from trash by its original path. Returns job_id."""
        job = TrashJob(
            id=str(uuid4()),
            op_type="restore",
            source=original_path
        )
        return self._submit(job, RestoreFromTrashRunnable)
    
    @Slot(result=str)
    def listTrash(self) -> str:
        """List all items in trash. Items emitted via itemListed signal. Returns job_id."""
        job = TrashJob(
            id=str(uuid4()),
            op_type="list"
        )
        return self._submit(job, ListTrashRunnable)
    
    @Slot(result=str)
    def emptyTrash(self) -> str:
        """Permanently delete all items in trash. Returns job_id."""
        job = TrashJob(
            id=str(uuid4()),
            op_type="empty"
        )
        return self._submit(job, EmptyTrashRunnable)
    
    @Slot(str)
    def cancel(self, job_id: str):
        """Cancel a running trash operation."""
        with QMutexLocker(self._mutex):
            job = self._jobs.get(job_id)
            if job:
                job.cancellable.cancel()
    
    def cancelAll(self):
        """Cancel all running trash operations."""
        with QMutexLocker(self._mutex):
            for job in self._jobs.values():
                job.cancellable.cancel()
