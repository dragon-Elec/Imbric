"""
GIO File Monitor - Directory watcher with debounce.
Moved from core/file_monitor.py
"""

from PySide6.QtCore import QObject, Signal, Slot, QTimer
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


class FileMonitor(QObject):
    """
    Watches a directory for file system changes using GIO.
    Emits signals that can trigger a view refresh.
    Includes Event Coalescing (Debounce) to prevent UI freezing during bulk operations.
    """

    fileCreated = Signal(str)
    fileDeleted = Signal(str)
    fileChanged = Signal(str)
    fileRenamed = Signal(str, str)
    directoryChanged = Signal()

    watchReady = Signal(str)
    watchFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor = None
        self._monitor_handler = None
        self._current_path = None

        from core.threading.worker_pool import AsyncWorkerPool

        self._pool = AsyncWorkerPool(max_concurrent=1, parent=self)
        self._pool.resultReady.connect(self._on_watch_result)
        self._pool.errorOccurred.connect(self._on_watch_error)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._emit_directory_changed)

    def _emit_directory_changed(self):
        self.directoryChanged.emit()

    @Slot(str)
    def watch(self, directory_path: str):
        self.stop()

        if directory_path.startswith(("recent://", "trash://")):
            return

        self._pool.clear()
        self._pool.enqueue(
            f"watch_{directory_path}",
            self._setup_monitor_task,
            priority=10,
            directory_path=directory_path,
        )

    @staticmethod
    def _setup_monitor_task(directory_path: str):
        gfile = Gio.File.new_for_commandline_arg(directory_path)
        monitor = gfile.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        return monitor

    def _on_watch_result(self, task_id: str, monitor):
        if monitor and self._current_path and task_id.endswith(self._current_path):
            self._monitor = monitor
            self._monitor_handler = self._monitor.connect("changed", self._on_changed)
            self.watchReady.emit(self._current_path)

    def _on_watch_error(self, task_id: str, error: str):
        self.watchFailed.emit(error)

    @Slot()
    def stop(self):
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

    def _on_changed(self, monitor, file, other_file, event_type):
        path = (file.get_path() or file.get_uri()) if file else None
        other_path = (
            (other_file.get_path() or other_file.get_uri()) if other_file else None
        )

        match event_type:
            case Gio.FileMonitorEvent.CREATED | Gio.FileMonitorEvent.MOVED_IN if path:
                self.fileCreated.emit(path)
                self._debounce_timer.start()

            case Gio.FileMonitorEvent.DELETED | Gio.FileMonitorEvent.MOVED_OUT if path:
                self.fileDeleted.emit(path)
                self._debounce_timer.start()

            case Gio.FileMonitorEvent.CHANGED if path:
                self.fileChanged.emit(path)

            case Gio.FileMonitorEvent.RENAMED if path and other_path:
                self.fileRenamed.emit(path, other_path)
                self._debounce_timer.start()

    @Slot(result=str)
    def currentPath(self) -> str:
        return self._current_path or ""
