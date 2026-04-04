from PySide6.QtCore import QObject, Signal, Slot, Property
from pathlib import Path
from gi.repository import Gio, GLib

# Import core components
from core.threading.worker_pool import AsyncWorkerPool
from core.backends.gio.desktop import (
    resolve_identity,
    enrich_breadcrumbs,
    get_breadcrumb_segments,
)
from core.backends.gio.scanner import FileScanner
from ui.services.row_builder import RowBuilder
from ui.bridges.app_bridge import AppBridge


class PaneContext(QObject):
    """
    Represents the full logic and state of a single view context.
    Formerly known as TabController. This drives the Scanner, Builder, and Breadcrumbs.
    """

    pathChanged = Signal(str)
    pathRejected = Signal()  # Triggers address bar shake animation
    selectPathsRequested = Signal(list)
    selectAllRequested = Signal()
    pathSegmentsChanged = Signal()  # [NEW] Emitted when async workers yield breadcrumbs

    def __init__(self, main_window, initial_path: str | None = None):
        super().__init__()
        self.mw = main_window
        self._current_path = initial_path or str(Path.home())

        # Core Components (Per-Tab)
        self.scanner = FileScanner()
        self.row_builder = RowBuilder()
        self.bridge = AppBridge(main_window)

        # Background workers for scanner
        registry = self.mw.registry
        self._count_worker = registry.create_count_worker()
        self._dimension_worker = registry.create_dimension_worker()
        if self._count_worker:
            self._count_worker.setParent(self)
        if self._dimension_worker:
            self._dimension_worker.setParent(self)
        self.scanner.set_workers(self._count_worker, self._dimension_worker)

        # Wire up components
        # 1. Scanner -> RowBuilder
        self.scanner.filesFound.connect(self._on_files_found)
        self.scanner.scanFinished.connect(self._on_scan_finished)
        self.scanner.fileAttributeUpdated.connect(self.row_builder.updateItem)
        self.scanner.singleFileScanned.connect(self._on_single_file_scanned)
        self.selectAllRequested.connect(self.row_builder.selectAllRequested)

        # 1.5. FileMonitor -> Surgical Updates
        self.mw.file_monitor.fileCreated.connect(self._on_file_created)
        self.mw.file_monitor.fileDeleted.connect(self._on_file_deleted)
        self.mw.file_monitor.fileRenamed.connect(self._on_file_renamed)

        # 2. Bridge reference
        # Duck-type the bridge's tab reference
        self.bridge._tab = self

        # Navigation History & Virtual Retention
        self.history_stack = []
        self.future_stack = []
        self._virtual_path = self._current_path  # Nemo-style future path retention
        self._is_history_nav = False
        self._current_session_id = ""
        self._selection = []

        # [NEW] Pre-parsed GFile for surgical updates. Zero-IO constructor.
        self._current_gfile = (
            Gio.File.new_for_commandline_arg(self._current_path)
            if self._current_path
            else None
        )

        # Background worker pool for resolving mounts/links without freezing UI
        self._nav_pool = AsyncWorkerPool(max_concurrent=2, parent=self)
        self._nav_pool.resultReady.connect(self._on_nav_worker_result)
        self._cached_segments = []

    def _on_nav_worker_result(self, task_id, result):
        if task_id.startswith("enrich_"):
            if result and task_id == f"enrich_{self._virtual_path}":
                self._cached_segments = result
                crumbs_str = " / ".join([s["name"] for s in self._cached_segments])
                print(f"[DEBUG-BREADCRUMB] Enriched Mode: {crumbs_str}")
                self.pathSegmentsChanged.emit()
        elif task_id.startswith("ident_"):
            # Update silently if Identity Worker found canonical resolution
            if (
                result
                and task_id == f"ident_{self._current_path}"
                and result != self._current_path
            ):
                self.current_path = result
                self._virtual_path = result
                self._cached_segments = []
                self.pathChanged.emit(self._current_path)

    @property
    def selection(self):
        """Returns the current list of selected file paths."""
        return self._selection

    @Slot(list)
    def updateSelection(self, paths):
        """Receive selection updates from QML."""
        self._selection = paths

    @Property(str, notify=pathChanged)
    def currentPath(self):
        return self._current_path

    @Property(QObject, constant=True)
    def fileScanner(self):
        return self.scanner

    @Property(QObject, constant=True)
    def rowBuilder(self):
        return self.row_builder

    @Property(QObject, constant=True)
    def appBridge(self):
        return self.bridge

    @property
    def current_path(self):
        return self._current_path

    @current_path.setter
    def current_path(self, val):
        if self._current_path != val:
            self._current_path = val
            # Update cache for surgical updates. new_for_commandline_arg is pure memory.
            self._current_gfile = Gio.File.new_for_commandline_arg(val) if val else None
            self.pathChanged.emit(val)

    @Property("QVariantList", notify=pathSegmentsChanged)
    def pathSegments(self):
        """Generates dynamic breadcrumb models using a two-phase Async Pattern."""
        if not self._virtual_path:
            return []

        if not self._cached_segments:
            self._build_fast_segments()

        return self._cached_segments

    def _build_fast_segments(self):
        """Phase A: delegating to specialized bridge for consistent path segments."""
        path = self._virtual_path
        if not path:
            self._cached_segments = []
            return

        # Use unified logic from desktop.py (Fast Mode)
        self._cached_segments = get_breadcrumb_segments(
            path, self._current_path, fast_mode=True
        )

        crumbs_str = " / ".join([s.get("name", "") for s in self._cached_segments])
        print(f"[DEBUG-BREADCRUMB] Fast Mode: {crumbs_str}")
        self.pathSegmentsChanged.emit()

        # Phase B: Fire Enrichment Worker for Full GIO mounts & icons
        # The worker correctly evaluates the identical desktop.py logic safely
        self._nav_pool.clear()  # cancel pending enrichments
        self._nav_pool.enqueue(
            f"enrich_{path}",
            enrich_breadcrumbs,
            virtual_path=path,
            active_path=self._current_path,
        )

    @Property(bool, notify=pathChanged)
    def canGoBack(self):
        return len(self.history_stack) > 0

    @Property(bool, notify=pathChanged)
    def canGoForward(self):
        return len(self.future_stack) > 0

    @Property(bool, notify=pathChanged)
    def canGoUp(self):
        return self._current_path != "/"

    def navigate_to(self, path: str):
        """Navigate this tab to a new path. Includes validation."""
        # Only strip leading whitespace (user input hygiene).
        # NEVER strip trailing — filenames can have trailing spaces.
        path = path.lstrip()
        if not path:
            return

        # Strip trailing slashes (but not for root "/")
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Assume raw path/string is accurate to update UI instantly without synchronous GIO Calls
        canonical_path = path

        # Nemo-style virtual path retention (keeps 'future' breadcrumbs active when digging back down)
        if self._virtual_path.startswith(canonical_path) and (
            len(canonical_path) == 1
            or len(self._virtual_path) == len(canonical_path)
            or self._virtual_path[len(canonical_path)] == "/"
        ):
            pass  # Keep virtual path as-is
        else:
            self._virtual_path = canonical_path

        if not self._is_history_nav:
            if self._current_path:
                self.history_stack.append(self._current_path)
            self.future_stack.clear()

        # Always update and emit even if same path (to ensure UI snaps shut)
        self.current_path = canonical_path
        self._cached_segments = []
        self._build_fast_segments()  # Pre-build segments and emit

        self.scan_current()
        self._is_history_nav = False

        # Phase 2: Deferred Identity resolution ensures canonical roots (e.g. MTP)
        self._nav_pool.enqueue(f"ident_{path}", resolve_identity, raw_path=path)

    def go_up(self):
        """Navigate to the parent directory."""
        # Async-safe string manipulation fallback for speedy UI, exact Identity Worker runs on navigation implicitly
        path = self._current_path
        if "://" in path:
            gfile = (
                Gio.File.new_for_uri(path)
                if "://" in path
                else Gio.File.new_for_path(path)
            )
            parent = gfile.get_parent()
            if parent:
                self.navigate_to(parent.get_uri())
        else:
            # Use PurePosixPath string approach for instant up level (fixes laggy Up Button)
            from pathlib import PurePosixPath

            parent_path = str(PurePosixPath(path).parent)
            if parent_path:
                self.navigate_to(parent_path)

    def scan_current(self):
        """Re-scans the current directory."""
        if self._current_path:
            self.row_builder.setFiles([])  # Clear UI
            self.scanner.scan_directory(self._current_path)
            self._current_session_id = self.scanner._session_id

    def go_back(self):
        if self.history_stack:
            prev = self.history_stack.pop()
            self.future_stack.append(self._current_path)

            # Virtual logic: going back retains the deeper virtual path so breadcrumbs stick around
            if self._virtual_path.startswith(prev) and (
                len(prev) == 1
                or len(self._virtual_path) == len(prev)
                or self._virtual_path[len(prev)] == "/"
            ):
                pass
            else:
                self._virtual_path = prev

            self._is_history_nav = True
            self.navigate_to(prev)

    def go_forward(self):
        if self.future_stack:
            next_path = self.future_stack.pop()
            self.history_stack.append(self._current_path)

            if self._virtual_path.startswith(next_path) and (
                len(next_path) == 1
                or len(self._virtual_path) == len(next_path)
                or self._virtual_path[len(next_path)] == "/"
            ):
                pass
            else:
                self._virtual_path = next_path

            self._is_history_nav = True
            self.navigate_to(next_path)

    def go_home(self):
        self.navigate_to(str(Path.home()))

    def _on_files_found(self, session_id: str, batch: list):
        if session_id != self._current_session_id:
            return
        self.row_builder.appendFiles(batch)

    def _on_single_file_scanned(self, session_id: str, item: dict):
        if session_id != self._current_session_id:
            return
        print(
            f"[DEBUG-SURGICAL] PaneContext: Received single file scan for {item.get('path')}"
        )
        self.row_builder.addSingleItem(item)

    def _is_in_current_dir(self, path: str) -> bool:
        """Robust, non-blocking check if a path belongs to the current directory."""
        if not self._current_gfile or not path:
            return False

        # Fast-path: String prefix (99% of cases). No GIO overhead.
        if (
            parent := path.rsplit("/", 1)[0] if "/" in path else ""
        ) == self._current_path:
            return True

        # Zero-IO Slow-path: GIO Equality (handles URI encoding/aliasing)
        # Using new_for_commandline_arg ensures it never touches the filesystem.
        try:
            return (
                (g := Gio.File.new_for_commandline_arg(path))
                .get_parent()
                .equal(self._current_gfile)
            )
        except Exception:
            return False

    @Slot(str)
    def _on_file_created(self, path: str):
        if self._is_in_current_dir(path):
            print(f"[DEBUG-SURGICAL] PaneContext: Adding {path}")
            self.scanner.scan_single_file(path)

    @Slot(str)
    def _on_file_deleted(self, path: str):
        if self._is_in_current_dir(path):
            print(f"[DEBUG-SURGICAL] PaneContext: Removing {path}")
            self.row_builder.removeSingleItem(path)

    @Slot(str, str)
    def _on_file_renamed(self, old_path: str, new_path: str):
        # Handle removal from current view
        if self._is_in_current_dir(old_path):
            self.row_builder.removeSingleItem(old_path)

        # Handle insertion/refresh in current view
        if self._is_in_current_dir(new_path):
            print(f"[DEBUG-SURGICAL] PaneContext: Renamed/Moved-in {new_path}")
            self.scanner.scan_single_file(new_path)

    def _on_scan_finished(self, session_id: str):
        if session_id != self._current_session_id:
            return
        self.row_builder.finishLoading()

        # Pending paths selection logic
        pending = self.bridge.selectPendingPaths()
        if pending:
            self.selectPathsRequested.emit(pending)

    def cleanup(self):
        """Cleanup resources when tab is closed."""
        self.scanner.cancel()

        # Disconnect surgical updates
        try:
            self.mw.file_monitor.fileCreated.disconnect(self._on_file_created)
        except:
            pass
        try:
            self.mw.file_monitor.fileDeleted.disconnect(self._on_file_deleted)
        except:
            pass
        try:
            self.mw.file_monitor.fileRenamed.disconnect(self._on_file_renamed)
        except:
            pass

        try:
            self.scanner.filesFound.disconnect()
        except:
            pass

    # --- View Actions ---
    def change_zoom(self, direction: int):
        """
        Adjust zoom level (Row Height) for this tab.
        direction: +1 (In), -1 (Out)
        """
        current_h = self.row_builder.getRowHeight()
        new_h = self.row_builder.calculate_next_zoom_height(direction)

        if new_h != current_h:
            self.row_builder.setRowHeight(new_h)
