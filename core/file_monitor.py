"""
FileMonitor.py

Wraps GIO's FileMonitor to watch a directory for changes.
Emits signals when files are added, removed, or modified.
"""

from PySide6.QtCore import QObject, Signal, Slot
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


class FileMonitor(QObject):
    """
    Watches a directory for file system changes using GIO.
    Emits signals that can trigger a view refresh.
    """
    
    # Signals
    fileCreated = Signal(str)      # path of new file
    fileDeleted = Signal(str)      # path of deleted file
    fileChanged = Signal(str)      # path of modified file
    fileRenamed = Signal(str, str) # (old_path, new_path)
    directoryChanged = Signal()    # Generic "something changed" signal
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor = None
        self._current_path = None
    
    # -------------------------------------------------------------------------
    # START MONITORING
    # -------------------------------------------------------------------------
    @Slot(str)
    def watch(self, directory_path: str):
        """
        Starts watching a directory for changes.
        Stops any previous monitoring.
        """
        # Stop existing monitor
        self.stop()
        
        self._current_path = directory_path
        
        try:
            gfile = Gio.File.new_for_path(directory_path)
            
            # Create monitor for directory
            self._monitor = gfile.monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES,  # Track moves/renames
                None  # Cancellable
            )
            
            # Connect to change signal
            self._monitor.connect("changed", self._on_changed)
            
            print(f"FileMonitor: Watching {directory_path}")
            
        except GLib.Error as e:
            print(f"FileMonitor: Failed to watch {directory_path}: {e}")
    
    # -------------------------------------------------------------------------
    # STOP MONITORING
    # -------------------------------------------------------------------------
    @Slot()
    def stop(self):
        """
        Stops monitoring the current directory.
        """
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
            self._current_path = None
    
    # -------------------------------------------------------------------------
    # INTERNAL: GIO Callback
    # -------------------------------------------------------------------------
    def _on_changed(self, monitor, file, other_file, event_type):
        """
        Called by GIO when something in the watched directory changes.
        """
        path = file.get_path() if file else None
        other_path = other_file.get_path() if other_file else None
        
        # Map GIO events to our signals
        if event_type == Gio.FileMonitorEvent.CREATED:
            if path:
                self.fileCreated.emit(path)
                self.directoryChanged.emit()
                
        elif event_type == Gio.FileMonitorEvent.DELETED:
            if path:
                self.fileDeleted.emit(path)
                self.directoryChanged.emit()
                
        elif event_type == Gio.FileMonitorEvent.CHANGED:
            if path:
                self.fileChanged.emit(path)
                # Don't emit directoryChanged for content changes (too noisy)
                
        elif event_type == Gio.FileMonitorEvent.RENAMED:
            if path and other_path:
                self.fileRenamed.emit(path, other_path)
                self.directoryChanged.emit()
                
        elif event_type == Gio.FileMonitorEvent.MOVED_IN:
            if path:
                self.fileCreated.emit(path)
                self.directoryChanged.emit()
                
        elif event_type == Gio.FileMonitorEvent.MOVED_OUT:
            if path:
                self.fileDeleted.emit(path)
                self.directoryChanged.emit()
    
    # -------------------------------------------------------------------------
    # PROPERTY
    # -------------------------------------------------------------------------
    @Slot(result=str)
    def currentPath(self) -> str:
        """
        Returns the currently watched path.
        """
        return self._current_path or ""
