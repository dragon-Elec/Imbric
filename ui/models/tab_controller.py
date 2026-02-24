from PySide6.QtCore import QObject, Signal, Slot, Property
from pathlib import Path
from gi.repository import Gio

# Import core components
from core.gio_bridge.scanner import DirectoryReader
from ui.services.row_builder import RowBuilder
from ui.bridges.app_bridge import AppBridge

class TabController(QObject):
    """
    Represents the logic and state of a single browser tab.
    Replaces the old QWidget-based BrowserTab.
    """
    pathChanged = Signal(str)
    selectPathsRequested = Signal(list)
    selectAllRequested = Signal()
    
    def __init__(self, main_window, initial_path: str | None = None):
        super().__init__()
        self.mw = main_window
        self._current_path = initial_path or str(Path.home())
        
        # Core Components (Per-Tab)
        self.scanner = DirectoryReader()
        self.row_builder = RowBuilder()
        self.bridge = AppBridge(main_window)
        
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
        
        # Navigation History
        self.history_stack = []
        self.future_stack = []
        self._is_history_nav = False
        self._current_session_id = ""
        self._selection = []

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
            self.pathChanged.emit(val)

    def navigate_to(self, path: str):
        """Navigate this tab to a new path."""
        if not self._is_history_nav:
            if self._current_path:
                self.history_stack.append(self._current_path)
            self.future_stack.clear()
        
        self.current_path = path
        self.scan_current()
        self._is_history_nav = False

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
            self._is_history_nav = True
            self.navigate_to(prev)

    def go_forward(self):
        if self.future_stack:
            next_path = self.future_stack.pop()
            self.history_stack.append(self._current_path)
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
        print(f"[DEBUG-SURGICAL] TabController: Received single file scan for {item.get('path')}")
        self.row_builder.addSingleItem(item)

    @Slot(str)
    def _on_file_created(self, path: str):
        print(f"[DEBUG-SURGICAL] TabController: _on_file_created: {path} | Current path: {self._current_path}")
        parent_gfile = Gio.File.parse_name(path).get_parent()
        current_gfile = Gio.File.parse_name(self._current_path)
        if parent_gfile and parent_gfile.equal(current_gfile):
            self.scanner.scan_single_file(path)

    @Slot(str)
    def _on_file_deleted(self, path: str):
        print(f"[DEBUG-SURGICAL] TabController: _on_file_deleted: {path} | Current path: {self._current_path}")
        parent_gfile = Gio.File.parse_name(path).get_parent()
        current_gfile = Gio.File.parse_name(self._current_path)
        if parent_gfile and parent_gfile.equal(current_gfile):
            self.row_builder.removeSingleItem(path)

    @Slot(str, str)
    def _on_file_renamed(self, old_path: str, new_path: str):
        print(f"[DEBUG-SURGICAL] TabController: _on_file_renamed: {old_path} -> {new_path}")
        parent_gfile = Gio.File.parse_name(old_path).get_parent()
        current_gfile = Gio.File.parse_name(self._current_path)
        if parent_gfile and parent_gfile.equal(current_gfile):
            self.row_builder.removeSingleItem(old_path)
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
        try: self.mw.file_monitor.fileCreated.disconnect(self._on_file_created)
        except: pass
        try: self.mw.file_monitor.fileDeleted.disconnect(self._on_file_deleted)
        except: pass
        try: self.mw.file_monitor.fileRenamed.disconnect(self._on_file_renamed)
        except: pass
            
        try:
            self.scanner.filesFound.disconnect()
        except: pass

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
