from PySide6.QtCore import QAbstractListModel, Qt, Slot, Signal, QObject, QModelIndex

class SimpleListModel(QAbstractListModel):
    """
    A simple read-only list model for a single column.
    """
    NameRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    IsDirRole = Qt.UserRole + 3
    WidthRole = Qt.UserRole + 4
    HeightRole = Qt.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        
        item = self._items[index.row()]
        
        if role == SimpleListModel.NameRole:
            return item.get("name", "")
        elif role == SimpleListModel.PathRole:
            return item.get("path", "")
        elif role == SimpleListModel.IsDirRole:
            return item.get("isDir", False)
        elif role == SimpleListModel.WidthRole:
            return item.get("width", 0)
        elif role == SimpleListModel.HeightRole:
            return item.get("height", 0)
        
        return None

    def roleNames(self):
        return {
            SimpleListModel.NameRole: b"name",
            SimpleListModel.PathRole: b"path",
            SimpleListModel.IsDirRole: b"isDir",
            SimpleListModel.WidthRole: b"width",
            SimpleListModel.HeightRole: b"height"
        }

    def set_items(self, items):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def add_items(self, new_items):
        if not new_items:
            return
        
        begin = len(self._items)
        end = begin + len(new_items) - 1
        
        self.beginInsertRows(QModelIndex(), begin, end)
        self._items.extend(new_items)
        self.endInsertRows()


class ColumnSplitter(QObject):
    """
    The 'Dealer'. Manages N SimpleListModels and distributes items 
    round-robin style into them.
    """
    columnsChanged = Signal() # Emitted when column count changes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_count = 3 # Default
        self._column_models = []
        self._all_items = [] # Master list of all items
        
        self._rebuild_models()

    @property
    def column_models(self):
        return self._column_models

    @Slot(int)
    def setColumnCount(self, count):
        if count < 1 or count == self._column_count:
            return
        
        self._column_count = count
        self._rebuild_models()
        self._redistribute()
        self.columnsChanged.emit()

    @Slot(list)
    def setFiles(self, files):
        """
        Sets the master list of files and distributes them.
        """
        self._all_items = files
        self._redistribute()

    @Slot(list)
    def appendFiles(self, new_files):
        """
        Appends new files to the master list and distributes them
        incrementally (optimization possible, but full redistribute is safer for now
        to maintain order if we implement sorting later).
        
        For round-robin, appending at the end might desync unless we track 
        the last index. For now, let's just append to _all_items and redistribute.
        """
        self._all_items.extend(new_files)
        self._redistribute()

    def _rebuild_models(self):
        """
        Creates the correct number of SimpleListModels.
        """
        self._column_models = [SimpleListModel(self) for _ in range(self._column_count)]

    def _redistribute(self):
        """
        The Core 'Dealing' Logic.
        Splits self._all_items into N lists.
        """
        # Create N empty lists
        columns = [[] for _ in range(self._column_count)]
        
        # Deal items
        for i, item in enumerate(self._all_items):
            col_idx = i % self._column_count
            columns[col_idx].append(item)
        
        # Update models
        for i, model in enumerate(self._column_models):
            model.set_items(columns[i])
            
    # QML Accessor for the models
    @Slot(result=list)
    def getModels(self):
        return self._column_models
