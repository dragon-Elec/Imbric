"""
RowModel — QAbstractListModel that wraps RowBuilder's row data.

Each model index = one row. The model emits incremental update signals
(beginInsertRows/endInsertRows) so QML ListView only creates delegates
for visible rows instead of rebuilding the entire world.
"""

from PySide6.QtCore import QAbstractListModel, Qt, Slot, QModelIndex, QByteArray


class RowModel(QAbstractListModel):
    """
    List model where each row contains a list of file item dicts.

    Roles:
        RowDataRole (Qt.UserRole + 1): list[dict] — the items in this row
    """

    RowDataRole = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[list[dict]] = []

    # --- QAbstractListModel overrides ---

    def rowCount(self, parent=None):
        return len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != self.RowDataRole:
            return None
        return self._rows[index.row()]

    def roleNames(self):
        return {self.RowDataRole: QByteArray(b"rowData")}

    # --- Public API ---

    def setRows(self, rows: list[list[dict]]) -> None:
        """Replace all rows. Emits model reset."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def appendRows(self, new_rows: list[list[dict]]) -> None:
        """Append rows incrementally. QML only creates new delegates."""
        if not new_rows:
            return
        start = len(self._rows)
        end = start + len(new_rows) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._rows.extend(new_rows)
        self.endInsertRows()

    def clear(self) -> None:
        """Remove all rows."""
        if not self._rows:
            return
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    @Slot(int, result="QVariant")
    def getRow(self, index: int):
        """QML-accessible getter for a single row by index."""
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return []

    @Slot(result=int)
    def getRowCount(self) -> int:
        return len(self._rows)

    @Slot(result=list)
    def getAllItems(self) -> list:
        """Flatten all rows into a single list of items."""
        items = []
        for row in self._rows:
            items.extend(row)
        return items
