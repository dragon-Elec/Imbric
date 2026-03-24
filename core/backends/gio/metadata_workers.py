"""
GIO Metadata Workers - Background workers for file metadata operations.
Moved from core/gio_bridge/metadata.py
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImageReader
from core.threading.worker_pool import GioWorkerPool
from core.backends.gio.metadata import get_file_info


class ItemCountWorker(QObject):
    """Async Directory Item Counter using GioWorkerPool."""

    countReady = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = GioWorkerPool(max_concurrent=4, parent=self)
        self._pool.resultReady.connect(self._on_result)

    def _on_result(self, path: str, count: int) -> None:
        self.countReady.emit(path, count)

    @Slot(str, str)
    def enqueue(self, uri: str, path: str) -> None:
        self._pool.enqueue(path, self._count, priority=0, uri=uri)

    def _count(self, uri: str) -> int:
        try:
            gfile = Gio.File.new_for_commandline_arg(uri)
            enumerator = gfile.enumerate_children(
                "standard::name", Gio.FileQueryInfoFlags.NONE, None
            )
            count = 0
            while True:
                files = enumerator.next_files(200, None)
                if not files:
                    break
                count += len(files)
            enumerator.close(None)
            return count
        except Exception:
            return 0

    @Slot()
    def clear(self) -> None:
        self._pool.clear()


class DimensionWorker(QObject):
    """Async Image Dimension Reader using GioWorkerPool."""

    dimensionsReady = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = GioWorkerPool(max_concurrent=4, parent=self)
        self._pool.resultReady.connect(self._on_result)

    @Slot(str, str)
    def enqueue(self, uri: str, path: str):
        self._pool.enqueue(path, self._read_dims, priority=60, uri=uri, path=path)

    def _read_dims(self, uri: str, path: str):
        try:
            if path and path.startswith("/"):
                reader = QImageReader(path)
                if reader.canRead():
                    size = reader.size()
                    if size.width() > 0:
                        return (size.width(), size.height())

            gfile = Gio.File.new_for_commandline_arg(uri)
            if not gfile.is_native():
                info = get_file_info(uri, attributes="standard::target-uri")
                if info and info.target_uri:
                    gfile = Gio.File.new_for_commandline_arg(info.target_uri)

            local_path = gfile.get_path()
            if local_path:
                reader = QImageReader(local_path)
                if reader.canRead():
                    size = reader.size()
                    return (size.width(), size.height())
        except Exception:
            pass
        return (0, 0)

    def _on_result(self, identifier: str, res: tuple):
        if res:
            self.dimensionsReady.emit(identifier, res[0], res[1])

    @Slot()
    def clear(self):
        self._pool.clear()


class PropertiesWorker(QObject):
    """Async File Properties Reader using GioWorkerPool."""

    propertiesReady = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = GioWorkerPool(max_concurrent=2, parent=self)
        self._pool.resultReady.connect(self._on_result)

    def _on_result(self, path: str, props: dict) -> None:
        self.propertiesReady.emit(path, props)

    @Slot(str)
    def enqueue(self, path: str):
        self._pool.enqueue(path, self._fetch_props, priority=80, path=path)

    def _fetch_props(self, path: str) -> dict:
        info = get_file_info(path)
        if not info:
            return {}
        return {
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
            "created": datetime.fromtimestamp(info.created_ts).isoformat()
            if info.created_ts
            else "",
            "modified": datetime.fromtimestamp(info.modified_ts).isoformat()
            if info.modified_ts
            else "",
            "accessed": datetime.fromtimestamp(info.accessed_ts).isoformat()
            if info.accessed_ts
            else "",
        }

    @Slot(list)
    def enqueue_batch(self, paths: list):
        for p in paths:
            if p:
                self.enqueue(p)

    @Slot()
    def clear(self):
        self._pool.clear()
