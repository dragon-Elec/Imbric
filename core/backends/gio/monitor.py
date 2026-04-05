"""
GIO File Monitor - Directory watcher with debounce.

Uses a dedicated QThread running a GLib.MainLoop to dispatch GIO callbacks,
keeping all GIO I/O off the Qt main thread while ensuring signal delivery.
"""

from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThread
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


class _GLibThread(QThread):
    """
    Dedicated thread running a GLib.MainLoop.
    GIO monitors created on this thread get their callbacks dispatched here.
    """

    def __init__(self):
        super().__init__()
        self._context = GLib.MainContext.new()
        self._loop = None

    def run(self):
        self._context.push_thread_default()
        self._loop = GLib.MainLoop.new(self._context, False)
        self._loop.run()
        self._context.pop_thread_default()

    def stop(self):
        if self._loop:
            self._loop.quit()
        self.wait(2000)

    @property
    def context(self):
        return self._context


# Singleton: one GLib thread shared by all FileMonitor instances
_glib_thread = None


def _get_glib_thread() -> _GLibThread:
    global _glib_thread
    if _glib_thread is None:
        _glib_thread = _GLibThread()
        _glib_thread.setObjectName("ImbricGLibThread")
        _glib_thread.start()
    return _glib_thread


def _shutdown_glib_thread():
    global _glib_thread
    if _glib_thread is not None:
        _glib_thread.stop()
        _glib_thread = None


import atexit

atexit.register(_shutdown_glib_thread)


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
        self._glib_thread = _get_glib_thread()

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._emit_directory_changed)

    def _emit_directory_changed(self):
        self.directoryChanged.emit()

    @Slot(str)
    def watch(self, directory_path: str):
        """
        Starts watching a directory for changes.
        Stops any previous monitoring.
        Schedules monitor creation on the GLib thread (non-blocking).
        """
        self.stop()

        if directory_path.startswith(("recent://", "trash://")):
            return

        self._current_path = directory_path

        # Schedule monitor creation on the GLib thread
        GLib.idle_add(
            self._setup_monitor_task,
            directory_path,
            context=self._glib_thread.context,
        )

    def _setup_monitor_task(self, directory_path: str) -> bool:
        """Runs on the GLib thread. Creates the GIO monitor."""
        try:
            gfile = Gio.File.new_for_commandline_arg(directory_path)
            self._monitor = gfile.monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES,
                None,
            )
            # Keep strong reference to prevent GC
            self._on_changed_ref = self._on_changed
            self._monitor_handler = self._monitor.connect(
                "changed", self._on_changed_ref
            )

            # Emit watchReady on Qt main thread
            QTimer.singleShot(
                0,
                lambda: self.watchReady.emit(self._current_path),
            )
        except GLib.Error as e:
            error_msg = str(e)
            QTimer.singleShot(
                0,
                lambda: self.watchFailed.emit(error_msg),
            )

        return False  # Remove from idle (run once)

    @Slot()
    def stop(self):
        """Stops monitoring the current directory."""
        if self._monitor:
            # Cancel on the GLib thread
            GLib.idle_add(
                self._cancel_monitor,
                context=self._glib_thread.context,
            )
            self._monitor = None
            self._monitor_handler = None
            self._current_path = None

    def _cancel_monitor(self) -> bool:
        """Runs on the GLib thread."""
        if self._monitor:
            if self._monitor_handler:
                try:
                    self._monitor.disconnect(self._monitor_handler)
                except Exception:
                    pass
                self._monitor_handler = None
            self._monitor.cancel()
            self._monitor = None
        return False

    def _on_changed(self, monitor, file, other_file, event_type):
        """
        Called on the GLib thread. Marshals to Qt main thread via
        QTimer.singleShot(0) before emitting signals.
        """
        path = (file.get_path() or file.get_uri()) if file else None
        other_path = (
            (other_file.get_path() or other_file.get_uri()) if other_file else None
        )

        # Marshal to Qt main thread
        QTimer.singleShot(
            0,
            lambda et=event_type, p=path, op=other_path: self._handle_event(et, p, op),
        )

    def _handle_event(self, event_type, path: str | None, other_path: str | None):
        """Runs on the Qt main thread. Dispatches GIO events to Qt signals."""
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

            case Gio.FileMonitorEvent.MOVED if path and other_path:
                self.fileRenamed.emit(path, other_path)
                self._debounce_timer.start()

    @Slot(result=str)
    def currentPath(self) -> str:
        return self._current_path or ""
