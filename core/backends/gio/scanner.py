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
from core.backends.gio.metadata_workers import BatchProcessorWorker
from core.utils.path_classifier import classify


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

        self._enumeration_finished = False

        # Background workers - injected or lazy loaded
        self._count_worker = None
        self._dimension_worker = None
        self._factory = None  # Still kept for main-thread legacy if needed
        self._batch_processor = BatchProcessorWorker(self)
        self._batch_processor.batchProcessed.connect(self._on_batch_processed)
        self._batch_processor.allTasksDone.connect(self._on_all_tasks_done)

    def _on_batch_processed(self, session_id, processed_batch):
        if session_id.startswith("single_file_"):
            original_session = session_id[12:]
            if original_session == self._session_id and processed_batch:
                item = processed_batch[0]
                # Trigger workers for the single file
                if item["isDir"] and not item["isSymlink"] and self._count_worker:
                    self._count_worker.enqueue(item["uri"], item["path"])
                if (
                    item["mimeType"].startswith("image/")
                    and self._is_native
                    and self._dimension_worker
                ):
                    self._dimension_worker.enqueue(item["uri"], item["path"])

                self.singleFileScanned.emit(original_session, item)
            return

        if session_id != self._session_id:
            return

        if processed_batch:
            # Trigger background workers for the batch
            for item in processed_batch:
                if item["isDir"] and not item["isSymlink"] and self._count_worker:
                    self._count_worker.enqueue(item["uri"], item["path"])

                if (
                    item["mimeType"].startswith("image/")
                    and self._is_native
                    and self._dimension_worker
                ):
                    self._dimension_worker.enqueue(item["uri"], item["path"])

            self._batch_buffer.extend(processed_batch)
            if not self._emit_timer.isActive():
                self._emit_timer.start()

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
        caps = classify(path)
        if caps.is_native or caps.is_recent or caps.is_trash:
            query += "," + ",".join(self.NATIVE_ATTRIBUTES)

        self._cancellable = Gio.Cancellable()
        self._scan_start_time = GLib.get_monotonic_time()
        self._session_id = str(uuid4())
        self._enumeration_finished = False
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
        caps = classify(path)
        is_native = caps.is_native
        query = ",".join(self.BASE_ATTRIBUTES)
        if is_native or caps.is_recent or caps.is_trash:
            query += "," + ",".join(self.NATIVE_ATTRIBUTES)

        gfile.query_info_async(
            query,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            None,
            self._on_single_query_ready,
            None,
        )

    def _on_single_query_ready(self, gfile, result, user_data):
        try:
            info = gfile.query_info_finish(result)
            parent = gfile.get_parent()
            # Offload to background worker even for single files
            self._batch_processor.enqueue(
                "single_file_" + self._session_id,
                [info],
                parent.get_uri(),
                self._show_hidden,
                self._is_native,
            )
        except GLib.Error:
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

        self._batch_processor.clear()

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
            self._enumeration_finished = True
            self._check_all_finished()
            self._close_enumerator(stored_enumerator)
            return

        # Offload to background worker
        self._batch_processor.enqueue(
            self._session_id,
            file_infos,
            parent_gfile.get_uri(),
            self._show_hidden,
            self._is_native,
        )

        self._fetch_next_batch(stored_enumerator, parent_gfile, cancellable)

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

    def _on_all_tasks_done(self, session_id: str) -> None:
        """Handle allTasksDone signal from BatchProcessorWorker."""
        if session_id == self._session_id:
            self._check_all_finished()

    def _check_all_finished(self) -> None:
        """Emit scanFinished only if both enumeration and metadata tasks are done."""
        if self._enumeration_finished:
            # Note: We should ideally check if the worker pool is idle for this session.
            # since allTasksDone is only emitted when the pool drains for this session_id,
            # and next_files_async has returned an empty list, we are safe to finish.
            self.scanFinished.emit(self._session_id)
