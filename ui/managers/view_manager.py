"""
ViewManager — Layout, Selection, and Visual State

Consolidates:
- ColumnSplitter (Masonry Layout distribution)
- SelectionHelper (Rubberband geometry)
- Zoom Logic (Column count control)
- View Mode (Sorter integration)
"""

from PySide6.QtCore import QObject, Slot, Signal, QRectF, QAbstractListModel, QModelIndex, Qt
from core.sorter import Sorter

# --- Merged ColumnSplitter Logic ---

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
    IconSourceRole = Qt.UserRole + 9  # ADD NEW ROLE CONSTANT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list = []

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
        elif role == self.IconSourceRole:  # EXPOSE THIS
            return item.get("iconSource", "")
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
            self.IconSourceRole: b"iconSource",  # MAP ROLE TO QML NAME
            self.IsDirRole: b"isDir",
            self.WidthRole: b"width",
            self.HeightRole: b"height",
            self.SizeRole: b"size",
            self.DateModifiedRole: b"dateModified",
            self.ChildCountRole: b"childCount",
        }

    def set_items(self, items: list) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()
        
    @Slot(int, result=dict)
    def get(self, row: int) -> dict:
        """Expose item data to QML by index."""
        if 0 <= row < len(self._items):
            return self._items[row]
        return {}

    def updateItem(self, row: int, key: str, value) -> bool:
        if not (0 <= row < len(self._items)):
            return False
        self._items[row][key] = value
        
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
    columnsChanged = Signal()
    sortChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_count = 3
        self._column_models: list = []
        self._all_items: list = [] 
        self._sorted_items: list = []
        self._path_index: dict = {}
        
        self._sorter = Sorter(self)
        self._sorter.sortChanged.connect(self._on_sort_changed)
        
        self._rebuild_models()

    @property
    def sorter(self) -> Sorter:
        return self._sorter

    @property
    def column_models(self) -> list:
        return self._column_models

    @Slot(int)
    def setColumnCount(self, count: int) -> None:
        if count < 1 or count == self._column_count:
            return
        self._column_count = count
        self._rebuild_models()
        self._redistribute()
        self.columnsChanged.emit()

    @Slot(list)
    def setFiles(self, files: list) -> None:
        self._all_items = files
        self._redistribute()

    @Slot(list)
    def appendFiles(self, new_files: list) -> None:
        self._all_items.extend(new_files)
        self._redistribute()

    @Slot()
    def clear(self) -> None:
        self._all_items = []
        self._redistribute()

    def _rebuild_models(self) -> None:
        self._column_models = [SimpleListModel(self) for _ in range(self._column_count)]

    def _redistribute(self) -> None:
        self._sorted_items = self._sorter.sort(self._all_items)
        columns = [[] for _ in range(self._column_count)]
        
        for i, item in enumerate(self._sorted_items):
            col_idx = i % self._column_count
            columns[col_idx].append(item)
        
        self._path_index.clear()
        for col_idx, model in enumerate(self._column_models):
            model.set_items(columns[col_idx])
            for row_idx, item in enumerate(columns[col_idx]):
                self._path_index[item["path"]] = (col_idx, row_idx)

    def _on_sort_changed(self) -> None:
        self._redistribute()
        self.sortChanged.emit()

    @Slot(result=list)
    def getModels(self) -> list:
        return self._column_models

    @Slot(result=list)
    def getAllItems(self) -> list:
        return self._sorted_items
        
    @Slot(result="QObject*")
    def getSorter(self) -> Sorter:
        return self._sorter

    @Slot(str, str, object)
    def updateItem(self, path: str, attr: str, value) -> None:
        location = self._path_index.get(path)
        if location is None: return
        
        col_idx, row_idx = location
        model = self._column_models[col_idx]
        model.updateItem(row_idx, attr, value)
        
        for item in self._all_items:
            if item.get("path") == path:
                item[attr] = value
                break

# --- Selection Helper ---

class SelectionHelper(QObject):
    """
    Helper class to perform geometry intersection checks for rubberband selection.
    Instantiated per-tab.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(QObject, int, float, float, float, float, float, float, result=list)
    def getMasonrySelection(self, splitter, col_count, col_width, spacing, x, y, w, h):
        """
        Calculates selection based on theoretical Masonry layout.
        """
        if not splitter: return []
        
        # Access the sorted list from the splitter
        items = splitter.getAllItems() 
        if not items: return []
        
        selection_rect = QRectF(x, y, w, h).normalized()
        selected_paths = []
        
        col_y = [0.0] * col_count
        footer_height = 36
        
        for i, item in enumerate(items):
            # 1. Determine Column
            col_idx = i % col_count
            
            # 2. Determine X
            item_x = col_idx * (col_width + spacing)
            
            # 3. Determine Height
            width = item.get('width', 0)
            height = item.get('height', 0)
            is_dir = item.get('isDir', False)
            
            display_height = col_width # Fallback
            if is_dir:
                display_height = col_width * 0.8
            elif width > 0 and height > 0:
                display_height = (height / width) * col_width
            
            total_item_height = display_height + footer_height
            
            # 4. Determine Y
            item_y = col_y[col_idx]
            
            # 5. Check Intersection
            item_rect = QRectF(item_x, item_y, col_width, total_item_height)
            
            if selection_rect.intersects(item_rect):
                selected_paths.append(item.get('path'))
                
            # 6. Update Column Y
            col_y[col_idx] += total_item_height
            
        return selected_paths

# --- ViewManager (The Global Controller) ---

class ViewManager(QObject):
    zoomChanged = Signal(int)
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    @Slot()
    def zoom_in(self):
        if tab := self.mw.tab_manager.current_tab:
            tab.change_zoom(-1)
            self.zoomChanged.emit(tab._target_column_width) # logical approximation
        
    @Slot()
    def zoom_out(self):
        if tab := self.mw.tab_manager.current_tab:
            tab.change_zoom(1)
            self.zoomChanged.emit(tab._target_column_width)

    @Slot()
    def reset_zoom(self):
        if tab := self.mw.tab_manager.current_tab:
             # Reset logic? Tab doesn't expose reset currently, maybe set to default 75
             pass
        
    @Slot()
    def select_all(self):
        # Trigger QML selectAll
        if tab := self.mw.tab_manager.current_tab:
             root = tab.qml_view.rootObject()
             if root:
                 from PySide6.QtCore import QMetaObject, Q_ARG
                 QMetaObject.invokeMethod(root, "selectAll")

    @Slot()
    def toggle_hidden(self):
        if tab := self.mw.tab_manager.current_tab:
            current = tab.scanner.showHidden()
            tab.scanner.setShowHidden(not current)
            # Refresh to Apply
            tab.scan_current()
