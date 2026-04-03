"""
GIO Metadata Workers - Background workers for file metadata operations.
Moved from core/gio_bridge/metadata.py
"""

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GnomeDesktop", "3.0")
from gi.repository import Gio, GLib, GnomeDesktop
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImageReader
from core.threading.worker_pool import AsyncWorkerPool
from core.backends.gio.metadata import get_file_info
from core.backends.gio.helpers import _make_gfile, to_unix_timestamp
from core.utils.path_ops import generate_candidate_path


class ItemCountWorker(QObject):
    """Async Directory Item Counter using AsyncWorkerPool."""

    countReady = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = AsyncWorkerPool(max_concurrent=4, parent=self)
        self._pool.resultReady.connect(self._on_result)

    def _on_result(self, path: str, count: int) -> None:
        self.countReady.emit(path, count)

    @Slot(str, str)
    def enqueue(self, uri: str, path: str) -> None:
        self._pool.enqueue(path, self._count, priority=0, uri=uri)

    def _count(self, uri: str) -> int:
        count = 0
        enumerator = None
        try:
            gfile = Gio.File.new_for_commandline_arg(uri)
            enumerator = gfile.enumerate_children(
                "standard::name", Gio.FileQueryInfoFlags.NONE, None
            )
            while True:
                files = enumerator.next_files(200, None)
                if not files:
                    break
                count += len(files)
            return count
        except Exception:
            return 0
        finally:
            if enumerator:
                try:
                    enumerator.close(None)
                except Exception:
                    pass

    @Slot()
    def clear(self) -> None:
        self._pool.clear()


class DimensionWorker(QObject):
    """Async Image Dimension Reader using AsyncWorkerPool."""

    dimensionsReady = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = AsyncWorkerPool(max_concurrent=4, parent=self)
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
    """Async File Properties Reader using AsyncWorkerPool."""

    propertiesReady = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = AsyncWorkerPool(max_concurrent=2, parent=self)
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


class ExistenceWorker(QObject):
    """Async Existence Checker using AsyncWorkerPool."""

    existenceReady = Signal(str, bool)  # (task_id, exists)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = AsyncWorkerPool(max_concurrent=4, parent=self)
        self._pool.resultReady.connect(self._on_result)

    def _on_result(self, task_id: str, exists: bool) -> None:
        self.existenceReady.emit(task_id, exists)

    @Slot(str, str)
    def enqueue(self, task_id: str, path: str) -> None:
        self._pool.enqueue(task_id, self._check, priority=20, path=path)

    def _check(self, path: str) -> bool:
        return _make_gfile(path).query_exists(None)

    @Slot()
    def clear(self):
        self._pool.clear()


class UniqueNameWorker(QObject):
    """Async Unique Name Generator using AsyncWorkerPool."""

    uniqueNameReady = Signal(str, str)  # (task_id, unique_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = AsyncWorkerPool(max_concurrent=4, parent=self)
        self._pool.resultReady.connect(self._on_result)

    def _on_result(self, task_id: str, unique_path: str) -> None:
        self.uniqueNameReady.emit(task_id, unique_path)

    @Slot(str, str, str)
    def enqueue(self, task_id: str, dest_path: str, style: str = "copy") -> None:
        self._pool.enqueue(task_id, self._find_unique, priority=10, dest_path=dest_path, style=style)

    def _find_unique(self, dest_path: str, style: str) -> str:
        # Max attempts to avoid infinite loops on weird VFS
        for counter in range(0, 1000):
            candidate = generate_candidate_path(dest_path, counter, style=style)
            gfile = _make_gfile(candidate)
            if not gfile.query_exists(None):
                return candidate
        return dest_path

    @Slot()
    def clear(self):
        self._pool.clear()


class BatchProcessorWorker(QObject):
    """
    Offloads heavy FileScanner._process_batch logic to background threads.
    Handles MIME guessing and GObject-heavy thumbnail checks.
    """

    batchProcessed = Signal(str, list)  # (session_id, processed_batch)
    allTasksDone = Signal(str)  # (session_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Higher concurrency for CPU-bound thumbnail checks
        self._pool = AsyncWorkerPool(max_concurrent=8, parent=self)
        self._pool.resultReady.connect(self._on_result)
        self._pool.allTasksDone.connect(self.allTasksDone)

    def _on_result(self, session_id: str, processed_batch: list) -> None:
        self.batchProcessed.emit(session_id, processed_batch)

    @Slot(str, list, str, bool, bool)
    def enqueue(self, session_id: str, file_infos: list, parent_uri: str, show_hidden: bool, is_native: bool):
        self._pool.enqueue(
            session_id,
            self._process_background,
            priority=50,
            session_id=session_id,
            file_infos=file_infos,
            parent_uri=parent_uri,
            show_hidden=show_hidden,
            is_native=is_native
        )

    def _process_background(self, session_id: str, file_infos: list, parent_uri: str, show_hidden: bool, is_native: bool) -> list:
        processed = []
        # Create a thread-local factory instance
        factory = None
        if is_native:
            try:
                factory = GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)
            except Exception:
                factory = None

        parent_gfile = Gio.File.new_for_uri(parent_uri)

        for info in file_infos:
            is_hidden = info.get_attribute_boolean("standard::is-hidden")
            if not show_hidden and is_hidden:
                continue

            name = info.get_name()
            if name is None:
                continue

            child_gfile = parent_gfile.get_child(name)
            full_uri = child_gfile.get_uri()
            full_path = child_gfile.get_path() or full_uri

            file_type = info.get_file_type()
            is_dir = file_type == Gio.FileType.DIRECTORY
            mime_type = info.get_attribute_string("standard::content-type") or ""

            if not mime_type:
                guessed_type, _certain = Gio.content_type_guess(name, None)
                mime_type = guessed_type or ""

            thumb_path = info.get_attribute_byte_string("standard::thumbnail-path")
            is_visual = False
            
            if thumb_path:
                is_visual = True
            else:
                if not is_native:
                    is_visual = mime_type.startswith(("image/", "video/", "application/pdf"))
                else:
                    if factory:
                        mtime = to_unix_timestamp(info.get_modification_date_time())
                        try:
                            is_visual = factory.can_thumbnail(full_uri, mime_type, mtime)
                        except Exception:
                            is_visual = mime_type.startswith(("image/", "video/", "application/pdf"))
                    else:
                        is_visual = mime_type.startswith(("image/", "video/", "application/pdf"))

            is_symlink = info.get_attribute_boolean("standard::is-symlink")
            symlink_target = info.get_attribute_byte_string("standard::symlink-target") or "" if is_symlink else ""
            size = info.get_size()
            date_modified = to_unix_timestamp(info.get_modification_date_time())
            date_accessed = to_unix_timestamp(info.get_access_date_time())

            mode = info.get_attribute_uint32("unix::mode") if info.has_attribute("unix::mode") else 0
            uid = info.get_attribute_uint32("unix::uid") if info.has_attribute("unix::uid") else 0
            gid = info.get_attribute_uint32("unix::gid") if info.has_attribute("unix::gid") else 0

            icon_name = "" if is_visual else (mime_type if mime_type else "application-x-generic")

            processed.append({
                "name": name,
                "path": full_path,
                "uri": full_uri,
                "iconName": icon_name,
                "isDir": is_dir,
                "size": size,
                "mimeType": mime_type,
                "isVisual": is_visual,
                "isSymlink": is_symlink,
                "symlinkTarget": symlink_target,
                "dateModified": date_modified,
                "dateAccessed": date_accessed,
                "mode": mode,
                "uid": uid,
                "gid": gid,
                "childCount": -1 if (is_dir and not is_symlink) else 0,
                "width": 0,
                "height": 0,
                "trashOrigPath": info.get_attribute_byte_string("trash::orig-path") or "",
                "trashDeletionDate": info.get_attribute_string("trash::deletion-date") if info.has_attribute("trash::deletion-date") else "",
                "targetUri": info.get_attribute_string("standard::target-uri") if info.has_attribute("standard::target-uri") else "",
            })

        return processed

    @Slot()
    def clear(self):
        self._pool.clear()
