from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, QByteArray
from gi.repository import Gio

from ui.models.tab_controller import TabController


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
            gfile = Gio.File.parse_name(tab.current_path)
            return gfile.get_basename() or "Home"
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
