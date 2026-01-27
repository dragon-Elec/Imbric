"""
[NEW] Core File Workers
Contains shared definitions (Jobs, Signals) and Standard File Operations (Copy, Move, Rename).
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from PySide6.QtCore import QObject, Signal, QRunnable
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from core.metadata_utils import get_file_info

# =============================================================================
# SHARED UTILS (Global)
# =============================================================================

def build_conflict_payload(src_path, dest_path, src_info=None, dest_info=None, extra_src_data=None):
    """
    Standardized conflict payload generator.
    Ensures TransactionManager always gets consistent data structure.
    """
    # Lazy load info if not provided
    if not src_info:
        src_info = get_file_info(src_path)
    if not dest_info:
        dest_info = get_file_info(dest_path)

    # Base dictionary
    payload = {
        "error": "exists",
        "src_path": src_path,
        "dest_path": dest_path,
        "dest": {"size": dest_info.size, "mtime": dest_info.modified_ts} if dest_info else {},
        "src": {}
    }

    # Handle standard file info vs Trash info
    if src_info and hasattr(src_info, 'size'):
        payload["src"] = {"size": src_info.size, "mtime": src_info.modified_ts}
    
    # Merge specific trash data (deletion date) if provided
    if extra_src_data:
        payload["src"].update(extra_src_data)

    return payload

@dataclass
class FileJob:
    """Tracks a single file operation (Standard or Trash)."""
    id: str
    op_type: str              # "copy", "move", "trash", "restore", "rename", "createFolder", "list", "empty"
    source: str
    dest: str = ""            # Destination path (or new name for rename)
    transaction_id: str = ""  # Links this job to a larger transaction (batch)
    cancellable: Gio.Cancellable = field(default_factory=Gio.Cancellable)
    status: str = "pending"   # "pending", "running", "done", "cancelled", "error"
    skipped_files: List[str] = field(default_factory=list)
    overwrite: bool = False   # If True, overwrite existing files without prompt
    rename_to: str = ""       # Specific for Restore: if set, restore with this filename

class FileOperationSignals(QObject):
    """
    Signal hub for file operations.
    Runnables hold a reference and emit via QMetaObject.invokeMethod (wrapped here).
    """
    started = Signal(str, str, str)           # (job_id, op_type, source_path)
    progress = Signal(str, int, int)          # (job_id, current_bytes, total_bytes)
    finished = Signal(str, str, str, str, bool, str)  # (tid, job_id, op_type, result_path, success, message)
    operationError = Signal(str, str, str, str, str, object) # (tid, job_id, op_type, path, message, conflict_data)
    
    # Trash Specific Signals (Consolidated here)
    itemListed = Signal(object)             # TrashItem (for list operation)
    trashNotSupported = Signal(str, str)    # (path, error_message)

class FileOperationRunnable(QRunnable):
    """Base class for file operation runnables."""
    
    def __init__(self, job: FileJob, signals: FileOperationSignals):
        super().__init__()
        self.job = job
        self.signals = signals
        self._last_progress_time = 0
        self.setAutoDelete(True)
    
    def emit_started(self):
        self.job.status = "running"
        self.signals.started.emit(self.job.id, self.job.op_type, self.job.source)
    
    def emit_progress(self, current: int, total: int):
        now = time.time()
        # Throttle to 10Hz
        if now - self._last_progress_time > 0.1 or current == total:
            self._last_progress_time = now
            self.signals.progress.emit(self.job.id, current, total)
    
    def emit_finished(self, success: bool, message: str, result_override: str = None):
        self.job.status = "done" if success else "error"
        # Determine result path (default to dest, fall back to source)
        # For Move/Copy/Rename: dest is usually the result.
        # For Trash: source is the result (it's gone, or rather moved to trash).
        result_path = result_override if result_override is not None else (self.job.dest if self.job.dest else self.job.source)
        
        self.signals.finished.emit(
            self.job.transaction_id,
            self.job.id,
            self.job.op_type,
            result_path,
            success,
            message
        )

    def _progress_callback(self, current_bytes, total_bytes, user_data):
        """Gio progress callback adapter."""
        self.emit_progress(current_bytes, total_bytes)

    # Removed local build_conflict_data helper, using global build_conflict_payload

# =============================================================================
# STANDARD OPERATIONS
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
            
            if self.job.skipped_files:
                count = len(self.job.skipped_files)
                self.emit_finished(True, f"{self.job.dest}|PARTIAL:{count}")
            else:
                self.emit_finished(True, self.job.dest)
                
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.EXISTS:
                print(f"[FILE_OPS:{self.job.id[:8]}] CONFLICT: File exists at dest")
                conflict_data = build_conflict_payload(self.job.source, self.job.dest)
                self.signals.operationError.emit(self.job.transaction_id, self.job.id, "copy", self.job.dest, "Conflict detected", conflict_data)
                self.emit_finished(False, "Conflict detected")
            else:
                msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
                self.emit_finished(False, msg)
    
    def _recursive_copy(self, source, dest, cancellable):
        info = source.query_info("standard::type,standard::name", Gio.FileQueryInfoFlags.NONE, cancellable)
        file_type = info.get_file_type()
        
        if file_type == Gio.FileType.DIRECTORY:
            try:
                dest.make_directory_with_parents(cancellable)
            except GLib.Error:
                pass # Exists ok
            
            enumerator = None
            try:
                enumerator = source.enumerate_children("standard::name,standard::type", Gio.FileQueryInfoFlags.NONE, cancellable)
                for child_info in enumerator:
                    child_name = child_info.get_name()
                    self._recursive_copy(source.get_child(child_name), dest.get_child(child_name), cancellable)
            finally:
                if enumerator: enumerator.close(None)
        else:
            flags = Gio.FileCopyFlags.OVERWRITE if self.job.overwrite else Gio.FileCopyFlags.NONE
            source.copy(dest, flags, cancellable, self._progress_callback, None)

class MoveRunnable(FileOperationRunnable):
    """Handles move with directory merge support."""
    
    def run(self):
        self.emit_started()
        source = Gio.File.new_for_path(self.job.source)
        dest = Gio.File.new_for_path(self.job.dest)
        
        try:
            flags = Gio.FileCopyFlags.OVERWRITE if self.job.overwrite else Gio.FileCopyFlags.NONE
            source.move(dest, flags, self.job.cancellable, self._progress_callback, None)
            self.emit_finished(True, self.job.dest)
            
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.WOULD_MERGE or e.code == 29:
                # Merge Logic
                try:
                    self.job.skipped_files = []
                    self._recursive_move_merge(source, dest, self.job.cancellable)
                    if self.job.skipped_files:
                        self.emit_finished(True, f"{self.job.dest}|PARTIAL:{len(self.job.skipped_files)}")
                    else:
                        self.emit_finished(True, self.job.dest)
                except GLib.Error as merge_e:
                    msg = "Cancelled" if merge_e.code == Gio.IOErrorEnum.CANCELLED else str(merge_e)
                    self.emit_finished(False, msg)
            elif e.code == Gio.IOErrorEnum.EXISTS:
                conflict_data = build_conflict_payload(self.job.source, self.job.dest)
                self.signals.operationError.emit(self.job.transaction_id, self.job.id, "move", self.job.dest, "Conflict detected", conflict_data)
                self.emit_finished(False, "Conflict detected")
            else:
                msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
                self.emit_finished(False, msg)

    def _recursive_move_merge(self, source, dest, cancellable):
        enumerator = None
        local_skipped = False
        try:
            enumerator = source.enumerate_children("standard::name,standard::type", Gio.FileQueryInfoFlags.NONE, cancellable)
            for child_info in enumerator:
                child_name = child_info.get_name()
                child_source = source.get_child(child_name)
                child_dest = dest.get_child(child_name)
                
                flags = Gio.FileCopyFlags.OVERWRITE if self.job.overwrite else Gio.FileCopyFlags.NONE
                
                # If both are dirs, recurse
                if child_info.get_file_type() == Gio.FileType.DIRECTORY and child_dest.query_exists(cancellable):
                     # Check if dest is also dir
                     d_info = child_dest.query_info("standard::type", Gio.FileQueryInfoFlags.NONE, cancellable)
                     if d_info.get_file_type() == Gio.FileType.DIRECTORY:
                         self._recursive_move_merge(child_source, child_dest, cancellable)
                         continue

                try:
                    child_source.move(child_dest, flags, cancellable, self._progress_callback, None)
                except GLib.Error as e:
                    if e.code in [Gio.IOErrorEnum.CANCELLED, Gio.IOErrorEnum.EXISTS]: raise
                    self.job.skipped_files.append(child_source.get_path())
                    local_skipped = True
        finally:
            if enumerator: enumerator.close(None)
        
        # Cleanup empty source only if we moved everything locally
        if not local_skipped and not self.job.skipped_files:
            try:
                source.delete(cancellable)
            except GLib.Error:
                pass


class RenameRunnable(FileOperationRunnable):
    def run(self):
        self.emit_started()
        gfile = Gio.File.new_for_path(self.job.source)
        try:
            # dest holds the new NAME, not full path
            result = gfile.set_display_name(self.job.dest, self.job.cancellable)
            if result:
                # Ensure absolute path (Gio can return relative sometimes)
                parent = os.path.dirname(self.job.source)
                abs_path = os.path.join(parent, self.job.dest)
                self.emit_finished(True, "Success", result_override=abs_path)
            else:
                self.emit_finished(False, "Rename failed")
        except GLib.Error as e:
            # Check for conflict on rename
            if e.code == Gio.IOErrorEnum.EXISTS:
                 # Construct full dest path for conflict logic
                 parent = os.path.dirname(self.job.source)
                 dest_path = os.path.join(parent, self.job.dest)
                 conflict_data = build_conflict_payload(self.job.source, dest_path)
                 self.signals.operationError.emit(self.job.transaction_id, self.job.id, "rename", dest_path, "Conflict detected", conflict_data)
                 self.emit_finished(False, "Conflict detected")
            else:
                 msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
                 self.emit_finished(False, msg)

class CreateFolderRunnable(FileOperationRunnable):
    def run(self):
        self.emit_started()
        gfile = Gio.File.new_for_path(self.job.source)
        try:
            gfile.make_directory(self.job.cancellable)
            self.emit_finished(True, self.job.source)
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            if e.code != Gio.IOErrorEnum.CANCELLED:
                self.signals.operationError.emit(self.job.transaction_id, self.job.id, "createFolder", self.job.source, msg, None)
            self.emit_finished(False, msg)
