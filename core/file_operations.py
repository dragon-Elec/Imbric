"""
FileOperations.py

Non-blocking file operations using QThread + Gio.Cancellable.
Exposes Signals for progress/completion that UI can connect to.
"""

import os
from PySide6.QtCore import QObject, Signal, Slot, QThread
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


# =============================================================================
# WORKER CLASS (Runs in separate thread)
# =============================================================================
class _FileOperationWorker(QObject):
    """
    Internal worker that executes file operations in a separate thread.
    Do not instantiate directly - use FileOperations controller.
    """
    
    # Signals
    started = Signal(str, str)          # (operation_type, path)
    progress = Signal(str, 'qint64', 'qint64')    # (path, current_bytes, total_bytes)
    finished = Signal(str, str, bool, str)  # (operation_type, path, success, message)
    
    def __init__(self):
        super().__init__()
        self._cancellable = None
        self._current_path = ""
        self._last_progress_time = 0
    
    @Slot(str, str)
    def do_copy(self, source_path: str, dest_path: str):
        """Copy a file or directory recursively with progress reporting."""
        self._cancellable = Gio.Cancellable()
        self._current_path = source_path
        self.started.emit("copy", source_path)
        
        source = Gio.File.new_for_path(source_path)
        dest = Gio.File.new_for_path(dest_path)
        
        try:
            self._recursive_copy(source, dest, self._cancellable)
            self.finished.emit("copy", source_path, True, dest_path)
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            print(f"[FILE_OPS] copy FAILED: {msg}")
            self.finished.emit("copy", source_path, False, msg)

    def _recursive_copy(self, source, dest, cancellable):
        """Helper to recursively copy files/folders"""
        info = source.query_info(
            "standard::type,standard::name",
            Gio.FileQueryInfoFlags.NONE,
            cancellable
        )
        file_type = info.get_file_type()
        
        if file_type == Gio.FileType.DIRECTORY:
            # Create destination directory
            if not dest.make_directory_with_parents(cancellable):
                pass # Ignore if exists (might be merging logic later)
            
            # Enumerate children
            enumerator = source.enumerate_children(
                "standard::name,standard::type",
                Gio.FileQueryInfoFlags.NONE,
                cancellable
            )
            
            for child_info in enumerator:
                child_name = child_info.get_name()
                child_source = source.get_child(child_name)
                child_dest = dest.get_child(child_name)
                
                # Recurse
                QThread.msleep(1) # Yield to main thread (prevent GUI freeze)
                self._recursive_copy(child_source, child_dest, cancellable)
                
        else:
            # Regular file copy
            source.copy(
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                cancellable,
                self._progress_callback,
                None
            )
    
    @Slot(str, str)
    def do_move(self, source_path: str, dest_path: str):
        """Move a file with progress reporting."""
        self._cancellable = Gio.Cancellable()
        self._current_path = source_path
        self.started.emit("move", source_path)
        
        source = Gio.File.new_for_path(source_path)
        dest = Gio.File.new_for_path(dest_path)
        
        try:
            source.move(
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                self._cancellable,
                self._progress_callback,
                None
            )
            print(f"[FILE_OPS] move SUCCESS: {dest_path}")
            self.finished.emit("move", source_path, True, dest_path)
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            print(f"[FILE_OPS] move FAILED: {msg}")
            self.finished.emit("move", source_path, False, msg)
    
    @Slot(str)
    def do_trash(self, path: str):
        """Trash a file."""
        self._cancellable = Gio.Cancellable()
        self._current_path = path
        self.started.emit("trash", path)
        
        gfile = Gio.File.new_for_path(path)
        
        try:
            gfile.trash(self._cancellable)
            print(f"[FILE_OPS] trash SUCCESS: {path}")
            self.finished.emit("trash", path, True, "")
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            print(f"[FILE_OPS] trash FAILED: {msg}")
            self.finished.emit("trash", path, False, msg)
    
    @Slot(str, str)
    def do_rename(self, path: str, new_name: str):
        """Rename a file or folder."""
        self._cancellable = Gio.Cancellable()
        self._current_path = path
        self.started.emit("rename", path)
        
        gfile = Gio.File.new_for_path(path)
        
        try:
            result = gfile.set_display_name(new_name, self._cancellable)
            if result:
                new_path = result.get_path()
                self.finished.emit("rename", path, True, new_path)
            else:
                self.finished.emit("rename", path, False, "Rename failed")
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.finished.emit("rename", path, False, msg)
    
    @Slot(str)
    def do_create_folder(self, path: str):
        """Create a new folder."""
        self._cancellable = Gio.Cancellable()
        self._current_path = path
        self.started.emit("createFolder", path)
        
        gfile = Gio.File.new_for_path(path)
        
        try:
            gfile.make_directory(self._cancellable)
            self.finished.emit("createFolder", path, True, "")
        except GLib.Error as e:
            msg = "Cancelled" if e.code == Gio.IOErrorEnum.CANCELLED else str(e)
            self.finished.emit("createFolder", path, False, msg)
    
    @Slot()
    def cancel(self):
        """Cancel the current operation."""
        if self._cancellable:
            self._cancellable.cancel()
    
    def _progress_callback(self, current_bytes, total_bytes, user_data):
        """Called by Gio during copy/move. Throttled to prevent UI freeze."""
        import time
        now = time.time()
        if now - getattr(self, '_last_progress_time', 0) > 0.1 or current_bytes == total_bytes:
            self._last_progress_time = now
            self.progress.emit(self._current_path, current_bytes, total_bytes)


# =============================================================================
# CONTROLLER (Main thread interface)
# =============================================================================
class FileOperations(QObject):
    """
    Non-blocking file operations controller.
    
    All operations run in a background thread, emitting signals on completion.
    UI stays responsive during large file operations.
    
    Usage:
        file_ops = FileOperations()
        file_ops.operationCompleted.connect(on_done)
        file_ops.copy("/src/file.txt", "/dest/file.txt")
    """
    
    # Public signals (connect to these in UI)
    operationStarted = Signal(str, str)       # (operation_type, path)
    operationProgress = Signal(str, 'qint64', 'qint64') # (path, current_bytes, total_bytes)
    operationCompleted = Signal(str, str, str)     # (operation_type, path, result_data)
    operationError = Signal(str, str, str)    # (operation_type, path, error_message)

    # Internal signals to trigger worker (Cross-thread communication)
    _requestCopy = Signal(str, str)
    _requestMove = Signal(str, str)
    _requestTrash = Signal(str)
    _requestRename = Signal(str, str)
    _requestCreateFolder = Signal(str)
    _requestCancel = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create worker thread
        self._thread = QThread()
        self._worker = _FileOperationWorker()
        self._worker.moveToThread(self._thread)
        
        # Connect WORKER Output -> Controller Signals
        self._worker.started.connect(self.operationStarted)
        self._worker.progress.connect(self.operationProgress)
        self._worker.finished.connect(self._on_worker_finished)
        
        # Connect CONTROLLER Input -> Worker Slots (Thread Safe)
        self._requestCopy.connect(self._worker.do_copy)
        self._requestMove.connect(self._worker.do_move)
        self._requestTrash.connect(self._worker.do_trash)
        self._requestRename.connect(self._worker.do_rename)
        self._requestCreateFolder.connect(self._worker.do_create_folder)
        self._requestCancel.connect(self._worker.cancel)
        
        # Start thread
        self._thread.start()
    
    def _on_worker_finished(self, op_type: str, path: str, success: bool, message: str):
        """Route worker finished signal to appropriate public signal."""
        if success:
            self.operationCompleted.emit(op_type, path, message)
        else:
            self.operationError.emit(op_type, path, message)
    
    # -------------------------------------------------------------------------
    # PUBLIC API (Non-blocking)
    # -------------------------------------------------------------------------
    @Slot(str, str)
    def copy(self, source_path: str, dest_path: str):
        """Copy a file asynchronously."""
        # Emit signal to trigger slot in worker thread
        self._requestCopy.emit(source_path, dest_path)
    
    @Slot(str, str)
    def move(self, source_path: str, dest_path: str):
        """Move a file asynchronously."""
        self._requestMove.emit(source_path, dest_path)
    
    @Slot(str)
    def trash(self, path: str):
        """Move a file to trash asynchronously."""
        self._requestTrash.emit(path)
    
    @Slot(list)
    def trashMultiple(self, paths: list):
        """
        Trash multiple files.
        """
        for path in paths:
            self._requestTrash.emit(path)
    
    @Slot(str, str)
    def rename(self, path: str, new_name: str):
        """Rename a file or folder asynchronously."""
        self._requestRename.emit(path, new_name)
    
    @Slot(str)
    def createFolder(self, path: str):
        """Create a new folder asynchronously."""
        self._requestCreateFolder.emit(path)
    
    @Slot()
    def cancel(self):
        """Cancel the current operation."""
        self._requestCancel.emit()
    
    # -------------------------------------------------------------------------
    # SYNCHRONOUS OPERATIONS (Quick, don't need threading)
    # -------------------------------------------------------------------------
    @Slot(str, result=bool)
    def openWithDefaultApp(self, path: str) -> bool:
        """
        Opens the file with its default application.
        This is instant, no need for threading.
        """
        try:
            gfile = Gio.File.new_for_path(path)
            uri = gfile.get_uri()
            Gio.AppInfo.launch_default_for_uri(uri, None)
            return True
        except GLib.Error as e:
            self.operationError.emit("open", path, str(e))
            return False
    
    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------
    def shutdown(self):
        """Clean shutdown of worker thread. Call on app exit."""
        self._thread.quit()
        self._thread.wait()
