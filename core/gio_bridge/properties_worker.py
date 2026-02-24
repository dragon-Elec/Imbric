"""
[NEW] PropertiesWorker — Async File Properties Reader

Offloads the blocking Gio.File.query_info() call to a background thread
so that opening file properties on network drives (FTP, SMB, MTP) does
not freeze the UI.

Pattern: Identical to DimensionWorker / ItemCountWorker.
"""

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from core.metadata_utils import get_file_info


class PropertiesRunnable(QRunnable):
    """Background task to query full file metadata via Gio."""

    def __init__(self, path: str, emitter):
        super().__init__()
        self.path = path
        self._emit = emitter
        self.setAutoDelete(True)

    def run(self):
        info = get_file_info(self.path)
        if info is None:
            self._emit(self.path, {})
            return

        from datetime import datetime

        result = {
            "path": info.path,
            "name": info.name,
            "size": info.size,
            "size_human": info.size_human,
            "is_dir": info.is_dir,
            "is_symlink": info.is_symlink,
            "symlink_target": info.symlink_target,
            "mime_type": info.mime_type,
            "permissions": info.permissions_str,
            "owner": info.owner,
            "group": info.group,
            "created": datetime.fromtimestamp(info.created_ts).isoformat() if info.created_ts else "",
            "modified": datetime.fromtimestamp(info.modified_ts).isoformat() if info.modified_ts else "",
            "accessed": datetime.fromtimestamp(info.accessed_ts).isoformat() if info.accessed_ts else "",
        }
        self._emit(self.path, result)


class PropertiesWorker(QObject):
    """
    Manages background file property queries.

    Usage:
        worker = PropertiesWorker(parent)
        worker.propertiesReady.connect(on_properties)
        worker.enqueue("/path/to/file")
    """

    # Signal: (path, properties_dict)
    propertiesReady = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()

    def enqueue(self, path: str):
        """Queue a file for async property reading."""
        task = PropertiesRunnable(path, self.propertiesReady.emit)
        self._pool.start(task)

    def enqueue_batch(self, paths: list):
        """Queue multiple files for async property reading."""
        for p in paths:
            if p:
                self.enqueue(p)
