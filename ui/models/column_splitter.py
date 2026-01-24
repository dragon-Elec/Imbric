"""
ColumnSplitter — Masonry Layout Distribution

The 'Dealer' that distributes files across N columns using round-robin.
Integrates with Sorter to apply sort order before distributing.

Features:
- Creates N SimpleListModel instances for QML binding
- Round-robin distribution preserves sort order
- Re-sorts on sort preference change
- Exposes models to QML via getModels()
"""

from PySide6.QtCore import QAbstractListModel, Qt, Slot, Signal, QObject, QModelIndex

from core.sorter import Sorter


class SimpleListModel(QAbstractListModel):
    """
    A simple read-only list model for a single column.
    
    Exposes file metadata to QML delegates.
    """
    
    # Role constants
    NameRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    IsDirRole = Qt.UserRole + 3
    WidthRole = Qt.UserRole + 4
    HeightRole = Qt.UserRole + 5
    SizeRole = Qt.UserRole + 6
    DateModifiedRole = Qt.UserRole + 7
    ChildCountRole = Qt.UserRole + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        
        item = self._items[index.row()]
        
        if role == self.NameRole:
            return item.get("name", "")
        elif role == self.PathRole:
            return item.get("path", "")
        elif role == self.IsDirRole:
            return item.get("isDir", False)
        elif role == self.WidthRole:
            return item.get("width", 0)
        elif role == self.HeightRole:
            return item.get("height", 0)
        elif role == self.SizeRole:
            return item.get("size", 0)
        elif role == self.DateModifiedRole:
            return item.get("dateModified", 0)
        elif role == self.ChildCountRole:
            return item.get("childCount", 0)
        
        return None

    def roleNames(self) -> dict:
        return {
            self.NameRole: b"name",
            self.PathRole: b"path",
            self.IsDirRole: b"isDir",
            self.WidthRole: b"width",
            self.HeightRole: b"height",
            self.SizeRole: b"size",
            self.DateModifiedRole: b"dateModified",
            self.ChildCountRole: b"childCount",
        }

    def set_items(self, items: list[dict]) -> None:
        """Replace all items (triggers full model reset)."""
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def add_items(self, new_items: list[dict]) -> None:
        """Append items (incremental update)."""
        if not new_items:
            return
        
        begin = len(self._items)
        end = begin + len(new_items) - 1
        
        self.beginInsertRows(QModelIndex(), begin, end)
        self._items.extend(new_items)
        self.endInsertRows()

    @Slot(int, result=dict)
    def get(self, row: int) -> dict:
        """Expose item data to QML by index."""
        if 0 <= row < len(self._items):
            return self._items[row]
        return {}

    def updateItem(self, row: int, key: str, value) -> bool:
        """
        Update a single attribute of an item and emit dataChanged.
        
        Returns True if update was successful.
        """
        if not (0 <= row < len(self._items)):
            return False
        
        self._items[row][key] = value
        
        # Map key to role
        role_map = {
            "childCount": self.ChildCountRole,
            "size": self.SizeRole,
            "dateModified": self.DateModifiedRole,
        }
        
        role = role_map.get(key)
        if role:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [role])
        
        return True


class ColumnSplitter(QObject):
    """
    The 'Dealer' — Manages N SimpleListModels and distributes items.
    
    Integrates with Sorter to ensure files appear in sorted order.
    """
    
    columnsChanged = Signal()  # Column count changed
    sortChanged = Signal()      # Sort order changed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_count = 3
        self._column_models: list[SimpleListModel] = []
        self._all_items: list[dict] = []  # Master list (unsorted)
        self._sorted_items: list[dict] = []  # Cached sorted list (for SelectionHelper)
        self._path_index: dict[str, tuple[int, int]] = {}  # path -> (col_idx, row_idx)
        
        # Sorter instance
        self._sorter = Sorter(self)
        self._sorter.sortChanged.connect(self._on_sort_changed)
        
        self._rebuild_models()

    @property
    def sorter(self) -> Sorter:
        """Access the sorter for external configuration."""
        return self._sorter

    @property
    def column_models(self) -> list[SimpleListModel]:
        return self._column_models

    @Slot(int)
    def setColumnCount(self, count: int) -> None:
        """Change the number of columns."""
        if count < 1 or count == self._column_count:
            return
        
        self._column_count = count
        self._rebuild_models()
        self._redistribute()
        self.columnsChanged.emit()

    @Slot(list)
    def setFiles(self, files: list[dict]) -> None:
        """Set the master list of files (replaces existing)."""
        self._all_items = files
        self._redistribute()

    @Slot(list)
    def appendFiles(self, new_files: list[dict]) -> None:
        """
        Append new files to the master list.
        
        Triggers a full redistribute to maintain sort order.
        """
        self._all_items.extend(new_files)
        self._redistribute()

    @Slot()
    def clear(self) -> None:
        """Clear all items."""
        self._all_items = []
        self._redistribute()

    def _rebuild_models(self) -> None:
        """Create the correct number of SimpleListModels."""
        self._column_models = [SimpleListModel(self) for _ in range(self._column_count)]

    def _redistribute(self) -> None:
        """
        Sort items and distribute across columns.
        
        This is the core 'Dealing' logic:
        1. Sort all items using current sort settings
        2. Cache sorted list for SelectionHelper
        3. Deal items round-robin into N columns
        4. Update column models
        """
        # Sort first and cache for SelectionHelper
        self._sorted_items = self._sorter.sort(self._all_items)
        
        # Create N empty lists
        columns: list[list[dict]] = [[] for _ in range(self._column_count)]
        
        # Deal items round-robin
        for i, item in enumerate(self._sorted_items):
            col_idx = i % self._column_count
            columns[col_idx].append(item)
        
        # Update models and build path index
        self._path_index.clear()
        for col_idx, model in enumerate(self._column_models):
            model.set_items(columns[col_idx])
            # Build index
            for row_idx, item in enumerate(columns[col_idx]):
                self._path_index[item["path"]] = (col_idx, row_idx)

    def _on_sort_changed(self) -> None:
        """Re-sort and redistribute when sort settings change."""
        self._redistribute()
        self.sortChanged.emit()

    # -------------------------------------------------------------------------
    # QML ACCESSORS
    # -------------------------------------------------------------------------
    
    @Slot(result=list)
    def getModels(self) -> list[SimpleListModel]:
        """Get the list of column models for QML binding."""
        return self._column_models

    @Slot(result=list)
    def getAllItems(self) -> list[dict]:
        """
        Get the sorted list of all items.
        
        Returns cached sorted list that matches the visual display order.
        Used by SelectionHelper for rubberband geometry calculation.
        
        Note: Previously returned unsorted _all_items, causing BUG-007.
        """
        return self._sorted_items

    @Slot(result="QObject*")
    def getSorter(self) -> Sorter:
        """Expose the sorter to QML for sort control."""
        return self._sorter

    @Slot(str, str, object)
    def updateItem(self, path: str, attr: str, value) -> None:
        """
        Update a single attribute of an item by path.
        
        Used for async updates like childCount.
        """
        location = self._path_index.get(path)
        if location is None:
            return
        
        col_idx, row_idx = location
        model = self._column_models[col_idx]
        model.updateItem(row_idx, attr, value)
        
        # Also update master list
        for item in self._all_items:
            if item.get("path") == path:
                item[attr] = value
                break
