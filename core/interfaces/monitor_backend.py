"""
MonitorBackend ABC - Contract for directory watching.
"""

from PySide6.QtCore import QObject, Signal, Slot


class MonitorBackend(QObject):
    """Contract for directory watching."""

    fileCreated = Signal(str)
    fileDeleted = Signal(str)
    fileChanged = Signal(str)
    fileRenamed = Signal(str, str)
    directoryChanged = Signal()
    watchReady = Signal(str)
    watchFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str)
    def watch(self, directory_path: str) -> None:
        """Start watching a directory for changes."""
        pass

    @Slot()
    def stop(self) -> None:
        """Stop watching."""
        pass

    @Slot(result=str)
    def currentPath(self) -> str:
        """Get the currently watched path."""
        return ""
