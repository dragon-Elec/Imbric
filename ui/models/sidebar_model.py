from PySide6.QtCore import QAbstractListModel, Qt, Slot, Signal, QModelIndex, Property

class SectionItemsModel(QAbstractListModel):
    """Inner model representing items within a specific sidebar section (e.g., individual Drives)."""
    NAME_ROLE = Qt.UserRole + 1
    PATH_ROLE = Qt.UserRole + 2
    ICON_ROLE = Qt.UserRole + 3
    TYPE_ROLE = Qt.UserRole + 4
    IDENT_ROLE = Qt.UserRole + 5
    USAGE_ROLE = Qt.UserRole + 6
    MOUNTED_ROLE = Qt.UserRole + 7
    UNMOUNT_ROLE = Qt.UserRole + 8

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = items or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        
        item = self._items[index.row()]
        
        if role == self.NAME_ROLE: return item.get("name")
        if role == self.PATH_ROLE: return item.get("path")
        if role == self.ICON_ROLE: return item.get("icon", "folder")
        if role == self.TYPE_ROLE: return item.get("type", "bookmark")
        if role == self.IDENT_ROLE: return item.get("identifier")
        if role == self.USAGE_ROLE: return item.get("usage")
        if role == self.MOUNTED_ROLE: return item.get("isMounted", False)
        if role == self.UNMOUNT_ROLE: return item.get("canUnmount", False)
        
        return None

    def roleNames(self):
        return {
            self.NAME_ROLE: b"name",
            self.PATH_ROLE: b"path",
            self.ICON_ROLE: b"icon",
            self.TYPE_ROLE: b"type",
            self.IDENT_ROLE: b"identifier",
            self.USAGE_ROLE: b"usage",
            self.MOUNTED_ROLE: b"isMounted",
            self.UNMOUNT_ROLE: b"canUnmount"
        }

    def update_items(self, new_items):
        """Replaces the internal list cleanly using model resets."""
        self.beginResetModel()
        self._items = new_items
        self.endResetModel()


class SidebarModel(QAbstractListModel):
    """Outer model representing sections (e.g., Quick Access, Devices)."""
    TITLE_ROLE = Qt.UserRole + 1
    ICON_ROLE = Qt.UserRole + 2
    TYPE_ROLE = Qt.UserRole + 3
    COLLAPSED_ROLE = Qt.UserRole + 4
    ACTIONS_ROLE = Qt.UserRole + 5
    ITEMS_ROLE = Qt.UserRole + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize sections with empty Item Models
        self._sections = [
            {
                "title": "Quick Access",
                "icon": "star",
                "type": "GRID",
                "collapsed": False,
                "actions": ["Add", "Settings"],
                "items_model": SectionItemsModel(parent=self)
            },
            {
                "title": "Devices",
                "icon": "hard_drive",
                "type": "LIST",
                "collapsed": False,
                "actions": ["Refresh"],
                "items_model": SectionItemsModel(parent=self)
            }
        ]
        
        # [DEBUG] MOCK DATA FOR SCROLL TESTING (RETRY)
        for i in range(3):
            mock_items = [{"name": f"Mock Item {j}", "path": "", "icon": "folder"} for j in range(5)]
            self._sections.append({
                "title": f"MOCK SECTION {i}",
                "icon": "folder",
                "type": "LIST",
                "collapsed": False,
                "actions": [],
                "items_model": SectionItemsModel(items=mock_items, parent=self)
            })

    def rowCount(self, parent=QModelIndex()):
        return len(self._sections)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._sections)):
            return None
        
        sec = self._sections[index.row()]
        
        if role == self.TITLE_ROLE: return sec["title"]
        if role == self.ICON_ROLE: return sec["icon"]
        if role == self.TYPE_ROLE: return sec["type"]
        if role == self.COLLAPSED_ROLE: return sec["collapsed"]
        if role == self.ACTIONS_ROLE: return sec["actions"]
        if role == self.ITEMS_ROLE: return sec["items_model"] # Return inner model directly!
        
        return None

    def roleNames(self):
        return {
            self.TITLE_ROLE: b"title",
            self.ICON_ROLE: b"icon",
            self.TYPE_ROLE: b"type",
            self.COLLAPSED_ROLE: b"collapsed",
            self.ACTIONS_ROLE: b"actions",
            self.ITEMS_ROLE: b"itemsModel"
        }

    def update_section_items(self, title, items):
        """Finds the section and updates ONLY its inner model."""
        for sec in self._sections:
            if sec["title"] == title:
                sec["items_model"].update_items(items)
                return

    def set_section_collapsed(self, title, is_collapsed):
        """Updates the collapsed state for a section."""
        for i, sec in enumerate(self._sections):
            if sec["title"] == title:
                if sec["collapsed"] != is_collapsed:
                    sec["collapsed"] = is_collapsed
                    idx = self.index(i, 0)
                    self.dataChanged.emit(idx, idx, [self.COLLAPSED_ROLE])
                return
