from PySide6.QtCore import QObject, Signal, Property, Slot, Qt
from PySide6.QtGui import QCursor, QIcon
from ui.widgets.drag_helper import start_drag_session
from ui.services.conflict_resolver import ConflictResolver
from ui.dialogs.conflicts import ConflictAction
from core.services.search.worker import SearchWorker
from core.threading.worker_pool import AsyncWorkerPool


class AppBridge(QObject):
    pathChanged = Signal(str)
    targetCellWidthChanged = Signal(int)
    renameRequested = Signal(str)
    cutPathsChanged = Signal()  # Emitted when clipboard cut state changes

    # Search signals
    searchResultsFound = Signal(list)  # Batch of paths
    searchFinished = Signal(int)  # Total count
    searchError = Signal(str)  # Error message

    # Context Menu Signals
    requestContextMenu = Signal(list)  # paths: list of strings (empty for background)

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._target_cell_width = 75
        self._pending_select_paths = []  # Paths to select after next directory refresh
        self._pending_rename_path = (
            None  # Path to trigger rename after createFolder completes
        )

        # Initialize search worker
        self._search_worker = SearchWorker(self)
        self._search_worker.resultsFound.connect(self.searchResultsFound)
        self._search_worker.searchFinished.connect(self.searchFinished)
        self._search_worker.searchError.connect(self.searchError)

        # Async Rename Assessment
        self._rename_pool = AsyncWorkerPool(max_concurrent=1, parent=self)
        self._rename_pool.resultReady.connect(self._on_rename_assessed)

        # Connect to clipboard changes
        self.mw.clipboard.clipboardChanged.connect(self._on_clipboard_changed)

    def _on_clipboard_changed(self):
        self.cutPathsChanged.emit()

    @Property(list, notify=cutPathsChanged)
    def cutPaths(self):
        """Returns list of paths currently in cut state."""
        # Delegated to FileManager
        return self.mw.file_manager.get_cut_paths()

    @Slot(list)
    def startDrag(self, paths):
        """Initiates a system drag-and-drop operation via DragHelper."""
        start_drag_session(self.mw, paths)

    @Slot(list, str, str)
    def handleDrop(self, urls, dest_dir="", mode="auto"):
        """
        Handles files dropped onto the view or a folder.
        Delegated to FileManager.
        """
        self.mw.file_manager.handle_drop(urls, dest_dir, mode)

    @Slot(str)
    def openPath(self, path):
        self.mw.navigate_to(path)

    @Slot(list)
    def showContextMenu(self, paths):
        """Requests QML to show a context menu for the given paths."""
        self.requestContextMenu.emit(paths)

    @Slot()
    def showBackgroundContextMenu(self):
        """Requests QML to show a background context menu."""
        self.requestContextMenu.emit([])

    # _create_new_folder moved to FileManager

    @Slot(str, result=str)
    def getThumbnailPath(self, path: str) -> str:
        """
        [DEPRECATED] Check if a native GNOME thumbnail exists for the file.
        Returns direct file:// URL if cached, else fallback to image:// provider.

        NOTE: This method is no longer called from QML during scroll.
        Thumbnail URL resolution has been moved to RowBuilder._resolve_thumbnail_url()
        which pre-computes the URL at load time, eliminating blocking I/O from
        the render path. Kept for backward compatibility.
        """
        import hashlib
        import urllib.parse
        from pathlib import Path

        try:
            # 1. Construct canonical URI (file:///path/to/file)
            # Must be quote-encoded (e.g. " " -> "%20")
            uri = "file://" + urllib.parse.quote(path)

            # 2. GNOME Thumbnail Spec: MD5 of URI
            md5_hash = hashlib.md5(uri.encode("utf-8")).hexdigest()

            # 3. Check Large Cache (256px)
            # The standard location is ~/.cache/thumbnails/large/
            cache_dir = Path.home() / ".cache" / "thumbnails" / "large"
            thumb_path = cache_dir / f"{md5_hash}.png"

            if thumb_path.exists():
                # SUCCESS: Return direct path to bypass Python loader
                return f"file://{thumb_path}"

        except Exception as e:
            print(f"[AppBridge] Thumbnail lookup failed: {e}")

        # FALLBACK: Ask the generator to make one
        return f"image://thumbnail/{path}"

    @Slot(str, str)
    def renameFile(self, old_path, new_name):
        """
        Renames a file. Called from QML after user finishes editing.
        Defers synchronous path parsing to the background.
        """
        if not old_path or not new_name:
            return

        print(
            f"[AppBridge] Enqueueing rename assessment for '{old_path}' -> '{new_name}'"
        )
        self._rename_pool.enqueue(
            f"rename_{old_path}",
            self._assess_rename_task,
            priority=10,
            old_path=old_path,
            new_name=new_name,
        )

    @staticmethod
    def _assess_rename_task(old_path: str, new_name: str) -> dict | None:
        """Background worker: Parses paths and tests bounds without freezing the UI."""
        from gi.repository import Gio

        try:
            gfile = Gio.File.parse_name(old_path)
            parent = gfile.get_parent()
            if not parent:
                return None

            new_gfile = parent.get_child(new_name)
            new_path = new_gfile.get_path() or new_gfile.get_uri()

            # Check if name actually changed
            if old_path == new_path:
                return {"skip": True}

            return {
                "skip": False,
                "old_path": old_path,
                "new_path": new_path,
                "new_name": new_name,
            }
        except Exception as e:
            print(f"[AppBridge] Background rename assessment failed: {e}")
            return None

    def _on_rename_assessed(self, task_id: str, result: dict | None):
        """Main thread callback to continue rename after background parsed paths."""
        if not task_id.startswith("rename_") or not result:
            return

        if result.get("skip"):
            return

        old_path = result["old_path"]
        new_path = result["new_path"]
        new_name = result["new_name"]

        # [Phase 7 Fix] The ConflictResolver still hits check_exists,
        # but the main heavy parsing is offloaded.
        # Creates a single-use resolver for this rename op
        resolver = ConflictResolver(self.mw)
        action, final_dest = resolver.resolve_rename(old_path, new_path)

        if action == ConflictAction.CANCEL or action == ConflictAction.SKIP:
            return

        # Dispatch to Background Worker to handle the actual GIO rename IO
        from gi.repository import Gio

        final_gfile = Gio.File.parse_name(final_dest)
        final_name = final_gfile.get_basename()
        self.mw.file_ops.rename(old_path, final_name)

    @Slot()
    def paste(self):
        self.mw.file_manager.paste_to_current()

    def queueSelectionAfterRefresh(self, paths):
        """Queue paths to be selected after the next directory refresh."""
        self._pending_select_paths = paths

    def selectPendingPaths(self):
        """Called after directory refresh to select queued files. Returns and clears the queue."""
        paths = self._pending_select_paths
        self._pending_select_paths = []
        return paths

    @Property(int, notify=targetCellWidthChanged)
    def targetCellWidth(self):
        return self._target_cell_width

    @targetCellWidth.setter
    def targetCellWidth(self, val):
        if self._target_cell_width != val:
            self._target_cell_width = val
            self.targetCellWidthChanged.emit(val)

    @Slot(int)
    def zoom(self, delta):
        # FIX: Wheel Up (Positive) should Zoom In
        self.mw.view_manager.zoom_in() if delta > 0 else self.mw.view_manager.zoom_out()

    # -------------------------------------------------------------------------
    # SEARCH API
    # -------------------------------------------------------------------------

    @Slot(str, str, bool)
    def startSearch(self, directory: str, pattern: str, recursive: bool = True):
        """
        Start a file search in the background.

        Results are emitted via searchResultsFound signal in batches.
        """
        self._search_worker.start_search(directory, pattern, recursive)

    @Slot()
    def cancelSearch(self):
        """Cancel the current search."""
        self._search_worker.cancel()

    @Property(str, constant=True)
    def searchEngineName(self) -> str:
        """Returns the name of the current search engine (fd or scandir)."""
        return self._search_worker.engine_name
