"""
[NEW] Core File Workers
Contains shared definitions (Jobs, Signals) and Standard File Operations (Copy, Move, Rename).
"""


import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from PySide6.QtCore import QObject, Signal, QRunnable
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from core.metadata_utils import get_file_info

# =============================================================================
# GIO PATH HELPERS
# =============================================================================

def _make_gfile(path_or_uri: str) -> Gio.File:
    """Create Gio.File from local path or URI. Handles both transparently."""
    if '://' in path_or_uri:
        return Gio.File.new_for_uri(path_or_uri)
    return Gio.File.new_for_path(path_or_uri)

def _gfile_path(gfile: Gio.File) -> str:
    """Get usable path string. Returns local path if available, URI otherwise."""
    return gfile.get_path() or gfile.get_uri()

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
    op_type: str              # "copy", "move", "trash", "restore", "rename", "createFolder", "list", "empty", "transfer"
    source: str
    dest: str = ""            # Destination path (or new name for rename)
    transaction_id: str = ""  # Links this job to a larger transaction (batch)
    cancellable: Gio.Cancellable = field(default_factory=Gio.Cancellable)
    auto_rename: bool = False # [NEW] If True, automatically find a free name (For New Folder / Duplicate)
    skipped_files: List[str] = field(default_factory=list) # For partial success
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

    def _run_create_operation(self, op_type: str, target_path: str):
        """
        Shared logic for all create operations (folder, file, symlink).
        Subclasses must override _do_create(gfile) with the actual Gio call.
        """
        self.emit_started()

        if self.job.auto_rename:
            counter = 0
            while counter < 10000:
                candidate = generate_candidate_path(target_path, counter, style="number")
                gfile = _make_gfile(candidate)
                try:
                    self._do_create(gfile)
                    self.emit_finished(True, candidate, result_override=candidate)
                    return
                except GLib.Error as e:
                    if e.code == Gio.IOErrorEnum.EXISTS:
                        counter += 1
                        continue
                    if e.code != Gio.IOErrorEnum.CANCELLED:
                        self.signals.operationError.emit(
                            self.job.transaction_id, self.job.id,
                            op_type, candidate, str(e), None
                        )
                    self.emit_finished(False, str(e))
                    return
            self.emit_finished(False, "Auto-rename limit reached")
            return

        # Standard Create (Fail if Exists)
        gfile = _make_gfile(target_path)
        try:
            self._do_create(gfile)
            self.emit_finished(True, target_path)
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.EXISTS:
                conflict_data = build_conflict_payload(target_path, target_path)
                self.signals.operationError.emit(
                    self.job.transaction_id, self.job.id,
                    op_type, target_path, str(e), conflict_data
                )
                self.emit_finished(False, str(e))
            else:
                if e.code != Gio.IOErrorEnum.CANCELLED:
                    self.signals.operationError.emit(
                        self.job.transaction_id, self.job.id,
                        op_type, target_path, str(e), None
                    )
                self.emit_finished(False, str(e))

    def _do_create(self, gfile):
        """Override in subclass. Execute the actual Gio create call."""
        raise NotImplementedError

    # Removed local build_conflict_data helper, using global build_conflict_payload

def _split_name_ext(filename: str) -> tuple[str, str]:
    """Split filename into (base, ext). Handles .tar.gz and dotfiles."""
    if filename.endswith(".tar.gz"):
        return filename[:-7], ".tar.gz"
    dot = filename.rfind(".")
    if dot <= 0:
        return filename, ""
    return filename[:dot], filename[dot:]

def generate_candidate_path(base_path: str, counter: int, style: str = "copy") -> str:
    """Generate a candidate path for auto-renaming. Returns full path."""
    if counter == 0:
        return base_path
    gfile = _make_gfile(base_path)
    parent = gfile.get_parent()
    name, ext = _split_name_ext(gfile.get_basename())
    if style == "copy":
        suffix = " (Copy)" if counter == 1 else f" (Copy {counter})"
    else:
        suffix = f" ({counter})"
    return _gfile_path(parent.get_child(f"{name}{suffix}{ext}"))

# =============================================================================
# STANDARD OPERATIONS
# =============================================================================

class TransferRunnable(FileOperationRunnable):
    """
    Unified worker for Copy and Move.
    Implements Smart Transfer:
    - If Move + same device -> Atomic Rename.
    - If Move + different device -> Recursive Copy + Delete.
    - If Copy -> Recursive Copy.
    - Handles Atomic Auto-Rename and Recursive Merge.
    """
    
    def run(self):
        self.emit_started()
        
        # [NEW] Atomic Auto-Rename Loop
        # We loop until we successfully transfer without an EXISTS error
        base_dest = self.job.dest
        
        counter = 0
        # If explicitly copying to same path (Duplication), start with 1 (Copy)
        # to avoid trying to overwrite self (which might succeed/fail unpredictably)
        if _make_gfile(self.job.source).equal(_make_gfile(base_dest)):
            counter = 1
            
        max_retries = 10000 if self.job.auto_rename else 1
        
        while counter < max_retries:
            # 1. Calculate Candidate Path
            final_dest = generate_candidate_path(base_dest, counter, style="copy")

            src_file = _make_gfile(self.job.source)
            dst_file = _make_gfile(final_dest)
            
            try:
                self.job.skipped_files = []
                
                # 2. Decision Logic (SMART TRANSFER)
                if self.job.op_type == "move":
                    # Try atomic move first
                    try:
                        flags = (Gio.FileCopyFlags.OVERWRITE if self.job.overwrite else Gio.FileCopyFlags.NONE) | Gio.FileCopyFlags.ALL_METADATA | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
                        # No fallback yet, we want to detect cross-device
                        src_file.move(dst_file, flags | Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE, 
                                      self.job.cancellable, self._progress_callback, None)
                        self.emit_finished(True, "Success", result_override=final_dest)
                        return
                    except GLib.Error as e:
                        # If it's a cross-device move, or directory merge, handle manually
                        if e.code in [Gio.IOErrorEnum.NOT_SUPPORTED, Gio.IOErrorEnum.WOULD_MERGE, 29]:
                            # Cross-device move or merge -> Recursive copy + delete
                            # Note: Recursive transfer logic handles its own errors, we need to catch EXISTS there too?
                            # _recursive_transfer generally doesn't raise EXISTS for children unless it's the root I guess?
                            # Actually, if root exists, _recursive_transfer might fail if it's a file.
                            # But if it's a dir, it merges.
                            
                            # For auto-rename, we generally want to avoid merging into existing folder too?
                            # Nautilus auto-renames even if it's a folder to avoid merge if "Keep Both" is selected.
                            # So we should treat EXISTS as a conflict/retry trigger.
                            
                            # Let's check existence before recursive if we are auto-renaming to be safe?
                            # No, TOCTOU.
                            # `_recursive_transfer` checks file type.
                            self._recursive_transfer(src_file, dst_file, is_move=True)
                            if self.job.skipped_files:
                                self.emit_finished(True, f"Partial Success: {len(self.job.skipped_files)} skipped", result_override=final_dest)
                            else:
                                self.emit_finished(True, "Success", result_override=final_dest)
                            return
                        elif e.code == Gio.IOErrorEnum.EXISTS:
                            raise e # Trigger Retry Loop
                        else:
                            raise e
                else:
                    # Standard Copy
                    self._recursive_transfer(src_file, dst_file, is_move=False)
                    if self.job.skipped_files:
                        self.emit_finished(True, f"Partial Success: {len(self.job.skipped_files)} skipped", result_override=final_dest)
                    else:
                        self.emit_finished(True, "Success", result_override=final_dest)
                    return
                        
            except GLib.Error as e:
                if e.code == Gio.IOErrorEnum.EXISTS:
                    if self.job.auto_rename:
                        counter += 1
                        continue # RETRY with new name
                    else:
                        # Conflict!
                        conflict_data = build_conflict_payload(self.job.source, final_dest)
                        self.signals.operationError.emit(self.job.transaction_id, self.job.id, self.job.op_type, final_dest, str(e), conflict_data)
                        self.emit_finished(False, str(e))
                        return
                else:
                    if e.code != Gio.IOErrorEnum.CANCELLED:
                        self.signals.operationError.emit(self.job.transaction_id, self.job.id, self.job.op_type, final_dest, str(e), None)
                    self.emit_finished(False, str(e))
                    return
        
        # If loop finishes without return (counter maxed)
        self.emit_finished(False, "Auto-rename limit reached")

    def _recursive_transfer(self, source, dest, is_move=False):
        """Unified recursive transfer logic."""
        info = source.query_info("standard::type,standard::name", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, self.job.cancellable)
        file_type = info.get_file_type()
        
        if file_type == Gio.FileType.DIRECTORY:
            try:
                dest.make_directory_with_parents(self.job.cancellable)
            except GLib.Error as e:
                if e.code != Gio.IOErrorEnum.EXISTS:
                    raise e
            
            local_error = False
            enumerator = None
            try:
                enumerator = source.enumerate_children("standard::name,standard::type", Gio.FileQueryInfoFlags.NONE, self.job.cancellable)
                for child_info in enumerator:
                    child_name = child_info.get_name()
                    c_src = source.get_child(child_name)
                    c_dst = dest.get_child(child_name)
                    
                    try:
                        self._recursive_transfer(c_src, c_dst, is_move=is_move)
                    except GLib.Error as e:
                        if e.code in [Gio.IOErrorEnum.CANCELLED, Gio.IOErrorEnum.EXISTS]: raise
                        self.job.skipped_files.append(c_src.get_path())
                        local_error = True
            finally:
                if enumerator: enumerator.close(None)
            
            # If move and all children transferred, delete original dir
            if is_move and not local_error:
                try:
                    source.delete(self.job.cancellable)
                except:
                    pass
        else:
            # File Transfer
            flags = (Gio.FileCopyFlags.OVERWRITE if self.job.overwrite else Gio.FileCopyFlags.NONE) | Gio.FileCopyFlags.ALL_METADATA | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
            if is_move:
                source.move(dest, flags, self.job.cancellable, self._progress_callback, None)
            else:
                source.copy(dest, flags, self.job.cancellable, self._progress_callback, None)


class RenameRunnable(FileOperationRunnable):
    def run(self):
        self.emit_started()
        gfile = _make_gfile(self.job.source)
        try:
            # dest holds the new NAME, not full path
            result = gfile.set_display_name(self.job.dest, self.job.cancellable)
            if result:
                # Use the Gio.File returned by set_display_name for the correct path
                abs_path = _gfile_path(result)
                self.emit_finished(True, "Success", result_override=abs_path)
            else:
                self.emit_finished(False, str(e))
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.EXISTS:
                 src_gfile = _make_gfile(self.job.source)
                 dest_path = _gfile_path(src_gfile.get_parent().get_child(self.job.dest))
                 conflict_data = build_conflict_payload(self.job.source, dest_path)
                 self.signals.operationError.emit(self.job.transaction_id, self.job.id, "rename", dest_path, str(e), conflict_data)
                 self.emit_finished(False, str(e))
            else:
                 if e.code != Gio.IOErrorEnum.CANCELLED:
                     self.signals.operationError.emit(self.job.transaction_id, self.job.id, "rename", self.job.source, str(e), None)
                 self.emit_finished(False, str(e))

class CreateFolderRunnable(FileOperationRunnable):
    """Creates a new directory."""
    def run(self):
        self._run_create_operation("createFolder", self.job.source)

    def _do_create(self, gfile):
        gfile.make_directory(self.job.cancellable)


class CreateFileRunnable(FileOperationRunnable):
    """Creates an empty file."""
    def run(self):
        self._run_create_operation("createFile", self.job.source)

    def _do_create(self, gfile):
        stream = gfile.create(Gio.FileCreateFlags.NONE, self.job.cancellable)
        stream.close(None)


class CreateSymlinkRunnable(FileOperationRunnable):
    """Creates a symbolic link. source = target file, dest = link location."""
    def run(self):
        self._run_create_operation("createSymlink", self.job.dest)

    def _do_create(self, gfile):
        gfile.make_symbolic_link(self.job.source, self.job.cancellable)

