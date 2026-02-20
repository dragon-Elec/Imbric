from PySide6.QtCore import QAbstractListModel, Qt, QObject, Signal, Slot, Property, QModelIndex, QByteArray
from pathlib import Path
import os

# Import core components
from core.gio_bridge.scanner import FileScanner
from ui.managers.row_builder import RowBuilder
from ui.models.app_bridge import AppBridge

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
        self.scanner = FileScanner()
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
        if not os.path.isdir(path):
            return
        
        path = os.path.abspath(path)
        
        if not self._is_history_nav:
            if self._current_path and os.path.isdir(self._current_path):
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
        if os.path.dirname(path) == os.path.abspath(self._current_path):
            self.scanner.scan_single_file(path)

    @Slot(str)
    def _on_file_deleted(self, path: str):
        print(f"[DEBUG-SURGICAL] TabController: _on_file_deleted: {path} | Current path: {self._current_path}")
        if os.path.dirname(path) == os.path.abspath(self._current_path):
            self.row_builder.removeSingleItem(path)

    @Slot(str, str)
    def _on_file_renamed(self, old_path: str, new_path: str):
        print(f"[DEBUG-SURGICAL] TabController: _on_file_renamed: {old_path} -> {new_path}")
        if os.path.dirname(old_path) == os.path.abspath(self._current_path):
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


class TabListModel(QAbstractListModel):
    """
    A QAbstractListModel that exposes a list of TabController objects to QML.
    """
    TitleRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    ControllerRole = Qt.ItemDataRole.UserRole + 3
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.mw = main_window
        self._tabs: list[TabController] = []
    
    def rowCount(self, parent=QModelIndex()):
        return len(self._tabs)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._tabs):
            return None
        
        tab = self._tabs[index.row()]
        
        if role == self.TitleRole or role == Qt.ItemDataRole.DisplayRole:
            return os.path.basename(tab.current_path) or "Home"
        elif role == self.PathRole:
            return tab.current_path
        elif role == self.ControllerRole:
            return tab
            
        return None
    
    def roleNames(self):
        return {
            self.TitleRole: QByteArray(b"title"),
            self.PathRole: QByteArray(b"path"),
            self.ControllerRole: QByteArray(b"controller")
        }
    
    def add_tab(self, path: str | None = None) -> TabController:
        self.beginInsertRows(QModelIndex(), len(self._tabs), len(self._tabs))
        tab = TabController(self.mw, path)
        
        # Connect to path changed to update title in List
        tab.pathChanged.connect(self._on_tab_path_changed)
        
        self._tabs.append(tab)
        self.endInsertRows()
        
        # Start navigation
        tab.navigate_to(tab.current_path)
        return tab
    
    def remove_tab(self, index: int):
        if 0 <= index < len(self._tabs):
            self.beginRemoveRows(QModelIndex(), index, index)
            tab = self._tabs.pop(index)
            tab.cleanup()
            self.endRemoveRows()
            
    def get_tab(self, index: int) -> TabController | None:
        if 0 <= index < len(self._tabs):
            return self._tabs[index]
        return None
    
    def _on_tab_path_changed(self, path):
        # Find which tab sent this
        sender = self.sender()
        if sender in self._tabs:
            idx = self._tabs.index(sender)
            # Notify that data for this row has changed (Title and Path)
            index = self.index(idx, 0)
            self.dataChanged.emit(index, index, [self.TitleRole, self.PathRole])
