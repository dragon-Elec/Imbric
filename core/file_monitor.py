"""
FileMonitor.py

Wraps GIO's FileMonitor to watch a directory for changes.
Emits signals when files are added, removed, or modified.
"""

from PySide6.QtCore import QObject, Signal, Slot, QTimer
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from core.utils.gio_qtoast import GioWorkerPool


class FileMonitor(QObject):
    """
    Watches a directory for file system changes using GIO.
    Emits signals that can trigger a view refresh.
    
    Includes Event Coalescing (Debounce) to prevent UI freezing during bulk operations.
    """
    
    # Signals
    fileCreated = Signal(str)      # path of new file
    fileDeleted = Signal(str)      # path of deleted file
    fileChanged = Signal(str)      # path of modified file
    fileRenamed = Signal(str, str) # (old_path, new_path)
    directoryChanged = Signal()    # Generic "something changed" signal
    
    # Async Status Signals
    watchReady = Signal(str)       # Emitted when background watch is active
    watchFailed = Signal(str)      # Emitted if watch setup fails
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor = None
        self._monitor_handler = None
        self._current_path = None
        
        # [Step 1.1] Worker Pool for backgrounding GIO calls
        self._pool = GioWorkerPool(max_concurrent=1, parent=self)
        self._pool.resultReady.connect(self._on_watch_result)
        self._pool.errorOccurred.connect(self._on_watch_error)
        
        # Debounce Timer for directoryChanged
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200) # Wait 200ms
        self._debounce_timer.timeout.connect(self._emit_directory_changed)
        
    def _emit_directory_changed(self):
        """Actually emit the signal after quiet period."""
        self.directoryChanged.emit()

    # -------------------------------------------------------------------------
    # START MONITORING
    
    # -------------------------------------------------------------------------
    # START MONITORING
    # -------------------------------------------------------------------------
    @Slot(str)
    def watch(self, directory_path: str):
        """
        Starts watching a directory for changes.
        Stops any previous monitoring. Actual setup happens in background.
        """
        # Stop existing monitor
        self.stop()
        
        # [ZERO-TRUST FIX] Don't even try to watch virtual/relative backends that don't support inotify.
        if directory_path.startswith(("recent://", "trash://")):
             print(f"FileMonitor: Skipping live watch for virtual path {directory_path}")
             return

        # Fire background task — UI is NEVER blocked
        self._pool.clear()
        self._pool.enqueue(
            f"watch_{directory_path}",
            self._setup_monitor_task,
            priority=10,
            directory_path=directory_path
        )

    @staticmethod
    def _setup_monitor_task(directory_path: str):
        """Runs in background thread. Returns the GIO monitor object."""
        gfile = Gio.File.new_for_commandline_arg(directory_path)
        monitor = gfile.monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES,
            None
        )
        return monitor

    def _on_watch_result(self, task_id: str, monitor):
        """Called on Main Thread when background watch setup completes."""
        if monitor and self._current_path and task_id.endswith(self._current_path):
            self._monitor = monitor
            self._monitor_handler = self._monitor.connect("changed", self._on_changed)
            
            # Since GIO signals interleave via GLib-Qt integration, 
            # we just need the reference to stay alive here.
            self.watchReady.emit(self._current_path)
            print(f"FileMonitor: Now watching {self._current_path} (Async-Active)")

    def _on_watch_error(self, task_id: str, error: str):
        """Called if background watch setup fails (e.g. non-supported FS)."""
        print(f"FileMonitor: Background setup failed for {task_id}: {error}")
        self.watchFailed.emit(error)
    
    # -------------------------------------------------------------------------
    # STOP MONITORING
    # -------------------------------------------------------------------------
    @Slot()
    def stop(self):
        """
        Stops monitoring the current directory.
        """
        if self._monitor:
            if self._monitor_handler:
                try:
                    self._monitor.disconnect(self._monitor_handler)
                except Exception:
                    pass
                self._monitor_handler = None
                
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
        path = (file.get_path() or file.get_uri()) if file else None
        other_path = (other_file.get_path() or other_file.get_uri()) if other_file else None
        
        # Modern Python 3.11+ Dispatch
        match event_type:
            case Gio.FileMonitorEvent.CREATED | Gio.FileMonitorEvent.MOVED_IN if path:
                print(f"[DEBUG-SURGICAL] FileMonitor: CREATED/MOVED_IN {path}")
                self.fileCreated.emit(path)
                self._debounce_timer.start()

            case Gio.FileMonitorEvent.DELETED | Gio.FileMonitorEvent.MOVED_OUT if path:
                print(f"[DEBUG-SURGICAL] FileMonitor: DELETED/MOVED_OUT {path}")
                self.fileDeleted.emit(path)
                self._debounce_timer.start()

            case Gio.FileMonitorEvent.CHANGED if path:
                self.fileChanged.emit(path)

            case Gio.FileMonitorEvent.RENAMED if path and other_path:
                print(f"[DEBUG-SURGICAL] FileMonitor: RENAMED {path} -> {other_path}")
                self.fileRenamed.emit(path, other_path)
                self._debounce_timer.start()
    
    # -------------------------------------------------------------------------
    # PROPERTY
    # -------------------------------------------------------------------------
    @Slot(result=str)
    def currentPath(self) -> str:
        """
        Returns the currently watched path.
        """
        return self._current_path or ""
