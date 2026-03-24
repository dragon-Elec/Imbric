"""
GIO Scanner - Async Directory Enumeration.
Moved from core/gio_bridge/scanner.py
"""

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GnomeDesktop", "3.0")
from gi.repository import Gio, GLib, GnomeDesktop
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QTimer

from core.backends.gio.helpers import _make_gfile, _gfile_path, to_unix_timestamp


class FileScanner(QObject):
    """
    Async directory scanner using GIO.

    Signals:
        filesFound(str, list) - Emitted with (session_id, batch)
        scanFinished(str) - Emitted with session_id when scan completes
        scanError(str) - Emitted on fatal error
    """

    filesFound = Signal(str, list)
    scanFinished = Signal(str)
    scanError = Signal(str)
    fileAttributeUpdated = Signal(str, str, object)
    singleFileScanned = Signal(str, dict)

    BASE_ATTRIBUTES = [
        "standard::name",
        "standard::type",
        "standard::is-hidden",
        "standard::size",
        "standard::content-type",
        "standard::is-symlink",
        "standard::symlink-target",
        "time::modified",
        "time::access",
        "standard::thumbnail-path",
    ]

    NATIVE_ATTRIBUTES = [
        "unix::mode",
        "unix::uid",
        "unix::gid",
        "trash::orig-path",
        "trash::deletion-date",
        "standard::target-uri",
    ]

    BATCH_SIZE = 200
    EMIT_DEBOUNCE_MS = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancellable: Gio.Cancellable | None = None
        self._current_path: str | None = None
        self._show_hidden: bool = False
        self._is_trash: bool = False
        self._is_native: bool = True

        self._session_id: str = ""

        self._batch_buffer: list[dict] = []
        self._emit_timer = QTimer(self)
        self._emit_timer.setInterval(self.EMIT_DEBOUNCE_MS)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.timeout.connect(self._flush_buffer)

        # Background workers - injected or lazy loaded
        self._count_worker = None
        self._dimension_worker = None
        self._factory = None

    def set_workers(self, count_worker, dimension_worker):
        """Inject background workers for counting and dimensions."""
        self._count_worker = count_worker
        self._dimension_worker = dimension_worker
        if count_worker:
            count_worker.countReady.connect(self._on_count_ready)
        if dimension_worker:
            dimension_worker.dimensionsReady.connect(self._on_dimensions_ready)

    @property
    def current_path(self) -> str | None:
        return self._current_path

    @Slot(bool)
    def setShowHidden(self, show: bool) -> None:
        self._show_hidden = show

    @Slot(result=bool)
    def showHidden(self) -> bool:
        return self._show_hidden

    @Slot(str)
    def scan_directory(self, path: str) -> None:
        self.cancel()

        self._current_path = path
        self._is_trash = path.startswith("trash://")

        gfile = Gio.File.new_for_commandline_arg(path)
        self._is_native = gfile.is_native()

        query = ",".join(self.BASE_ATTRIBUTES)
        if self._is_native or path.startswith(("trash://", "recent://")):
            query += "," + ",".join(self.NATIVE_ATTRIBUTES)

        self._cancellable = Gio.Cancellable()
        self._scan_start_time = GLib.get_monotonic_time()
        self._session_id = str(uuid4())
        cancellable = self._cancellable

        gfile.enumerate_children_async(
            query,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            self._on_enumerate_ready,
            cancellable,
        )

    @Slot(str)
    def scan_single_file(self, path: str) -> None:
        gfile = Gio.File.new_for_commandline_arg(path)
        is_native = gfile.is_native()
        query = ",".join(self.BASE_ATTRIBUTES)
        if is_native or path.startswith(("trash://", "recent://")):
            query += "," + ",".join(self.NATIVE_ATTRIBUTES)
        try:
            info = gfile.query_info(query, Gio.FileQueryInfoFlags.NONE, None)
            parent = gfile.get_parent()
            batch = self._process_batch([info], parent)
            if batch:
                self.singleFileScanned.emit(self._session_id, batch[0])
        except GLib.Error as e:
            pass

    @Slot()
    def cancel(self) -> None:
        self._emit_timer.stop()
        self._batch_buffer.clear()

        if self._cancellable is not None:
            self._cancellable.cancel()
            self._cancellable = None

        if self._count_worker:
            self._count_worker.clear()
        if self._dimension_worker:
            self._dimension_worker.clear()

    def _on_enumerate_ready(
        self, source: Gio.File, result: Gio.AsyncResult, user_data
    ) -> None:
        cancellable = user_data
        if cancellable.is_cancelled():
            return

        try:
            enumerator = source.enumerate_children_finish(result)
        except GLib.Error as e:
            if cancellable.is_cancelled():
                return
            self.scanError.emit(f"Cannot open directory: {e.message}")
            return

        parent_path = source.get_path() or source.get_uri()
        if parent_path is None:
            self.scanError.emit("Invalid directory path")
            return

        self._fetch_next_batch(enumerator, source, cancellable)

    def _fetch_next_batch(
        self,
        enumerator: Gio.FileEnumerator,
        parent_gfile: Gio.File,
        cancellable: Gio.Cancellable,
    ) -> None:
        enumerator.next_files_async(
            self.BATCH_SIZE,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            self._on_batch_ready,
            (enumerator, parent_gfile, cancellable),
        )

    def _on_batch_ready(
        self, source_obj, result: Gio.AsyncResult, context: tuple
    ) -> None:
        stored_enumerator, parent_gfile, cancellable = context

        if cancellable.is_cancelled():
            self._close_enumerator(stored_enumerator)
            return

        try:
            file_infos = stored_enumerator.next_files_finish(result)
        except GLib.Error as e:
            if cancellable.is_cancelled():
                self._close_enumerator(stored_enumerator)
                return
            self.scanError.emit(f"Error reading directory: {e.message}")
            self._close_enumerator(stored_enumerator)
            return

        if not file_infos:
            self._flush_buffer()
            scan_duration_ms = (
                GLib.get_monotonic_time() - self._scan_start_time
            ) / 1000
            self.scanFinished.emit(self._session_id)
            self._close_enumerator(stored_enumerator)
            return

        batch = self._process_batch(file_infos, parent_gfile)

        if batch:
            self._batch_buffer.extend(batch)
            if not self._emit_timer.isActive():
                self._emit_timer.start()

        self._fetch_next_batch(stored_enumerator, parent_gfile, cancellable)

    def _process_batch(self, file_infos: list, parent_gfile: Gio.File) -> list[dict]:
        batch = []

        for info in file_infos:
            is_hidden = info.get_attribute_boolean("standard::is-hidden")
            if not self._show_hidden and is_hidden:
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
                if not self._is_native:
                    is_visual = mime_type.startswith(
                        ("image/", "video/", "application/pdf")
                    )
                else:
                    if self._factory is None:
                        self._factory = GnomeDesktop.DesktopThumbnailFactory.new(
                            GnomeDesktop.DesktopThumbnailSize.LARGE
                        )

                    mtime = (
                        info.get_modification_date_time().to_unix()
                        if info.get_modification_date_time()
                        else 0
                    )
                    try:
                        is_visual = self._factory.can_thumbnail(
                            full_uri, mime_type, mtime
                        )
                    except Exception:
                        is_visual = mime_type.startswith(
                            ("image/", "video/", "application/pdf")
                        )

            should_read_dimensions = mime_type.startswith("image/")

            is_symlink = info.get_attribute_boolean("standard::is-symlink")

            symlink_target = ""
            if is_symlink:
                symlink_target = (
                    info.get_attribute_byte_string("standard::symlink-target") or ""
                )

            size = info.get_size()

            modified_dt = info.get_modification_date_time()
            access_dt = info.get_access_date_time()
            date_modified = to_unix_timestamp(modified_dt)
            date_accessed = to_unix_timestamp(access_dt)

            mode = (
                info.get_attribute_uint32("unix::mode")
                if info.has_attribute("unix::mode")
                else 0
            )
            uid = (
                info.get_attribute_uint32("unix::uid")
                if info.has_attribute("unix::uid")
                else 0
            )
            gid = (
                info.get_attribute_uint32("unix::gid")
                if info.has_attribute("unix::gid")
                else 0
            )

            child_count = -1 if (is_dir and not is_symlink) else 0

            if is_dir and not is_symlink and self._count_worker:
                self._count_worker.enqueue(full_uri, full_path)

            icon_name = ""
            if not is_visual:
                icon_name = mime_type if mime_type else "application-x-generic"

            batch.append(
                {
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
                    "childCount": child_count,
                    "width": 0,
                    "height": 0,
                    "trashOrigPath": info.get_attribute_byte_string("trash::orig-path")
                    or "",
                    "trashDeletionDate": info.get_attribute_string(
                        "trash::deletion-date"
                    )
                    if info.has_attribute("trash::deletion-date")
                    else "",
                    "targetUri": info.get_attribute_string("standard::target-uri")
                    if info.has_attribute("standard::target-uri")
                    else "",
                }
            )

            if should_read_dimensions and self._is_native and self._dimension_worker:
                self._dimension_worker.enqueue(full_uri, full_path)

        return batch

    def _close_enumerator(self, enumerator: Gio.FileEnumerator) -> None:
        try:
            enumerator.close(None)
        except Exception:
            pass

    def _flush_buffer(self) -> None:
        """Emit all buffered files at once to reduce layout thrashing."""
        if self._batch_buffer and self._session_id:
            self.filesFound.emit(self._session_id, self._batch_buffer)
            self._batch_buffer = []

    def _on_dimensions_ready(self, identifier: str, width: int, height: int) -> None:
        """Handle dimensionsReady signal from DimensionWorker."""
        self.fileAttributeUpdated.emit(
            identifier, "dimensions", {"width": width, "height": height}
        )

    def _on_count_ready(self, path: str, count: int) -> None:
        """Handle countReady signal from ItemCountWorker."""
        self.fileAttributeUpdated.emit(path, "childCount", count)
