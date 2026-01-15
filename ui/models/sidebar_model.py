from PySide6.QtCore import QAbstractListModel, Qt, Slot, QModelIndex

from core.gio_bridge.bookmarks import BookmarksBridge
from core.gio_bridge.volumes import VolumesBridge

class SidebarModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    PATH_ROLE = Qt.UserRole + 2
    ICON_ROLE = Qt.UserRole + 3
    TYPE_ROLE = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bookmarks_bridge = BookmarksBridge()
        self._volumes_bridge = VolumesBridge()
        self._items = []
        self.refresh()

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        
        item = self._items[index.row()]
        
        if role == self.NAME_ROLE:
            return item.get("name")
        elif role == self.PATH_ROLE:
            return item.get("path")
        elif role == self.ICON_ROLE:
            return item.get("icon", "folder")
        elif role == self.TYPE_ROLE:
            return item.get("type", "bookmark")
        
        return None

    def roleNames(self):
        return {
            self.NAME_ROLE: b"name",
            self.PATH_ROLE: b"path",
            self.ICON_ROLE: b"icon",
            self.TYPE_ROLE: b"type"
        }

    @Slot()
    def refresh(self):
        self.beginResetModel()
        self._items = []
        
        # 1. Volumes
        self._items.extend(self._volumes_bridge.get_volumes())
        
        # Separator logic could go here
        
        # 2. Bookmarks
        self._items.extend(self._bookmarks_bridge.get_bookmarks())
        
        self.endResetModel()
