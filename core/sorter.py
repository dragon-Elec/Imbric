"""
[STUB] Sorter — File Sorting Logic

Provides sorting capabilities for file lists (by name, date, size, type).
Used by ColumnSplitter before distributing files to columns.

Usage:
    sorter = Sorter()
    sorted_files = sorter.sort(files, SortKey.NAME, ascending=True)
    
Integration:
    - ColumnSplitter calls sorter.sort() before redistribute()
    - UI provides dropdown/menu to change sort key
    - Sort preference persisted per-directory or globally
"""

from PySide6.QtCore import QObject, Signal, Slot
from enum import Enum, auto
from typing import List


class SortKey(Enum):
    """Available sort keys."""
    NAME = auto()           # Alphabetical by filename
    DATE_MODIFIED = auto()  # Most recent first
    DATE_CREATED = auto()   # Most recent first  
    SIZE = auto()           # Largest first
    TYPE = auto()           # By extension/mime-type


class Sorter(QObject):
    """
    Sorts file lists by various criteria.
    Stateless utility - can be shared across tabs.
    """
    
    # Emitted when sort preference changes (for UI sync)
    sortChanged = Signal(SortKey, bool)  # (key, ascending)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = SortKey.NAME
        self._ascending = True
        self._folders_first = True  # Always keep folders at top
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(list, result=list)
    def sort(self, files: List[dict], key: SortKey = None, ascending: bool = None) -> List[dict]:
        """
        Sort a list of file dicts.
        
        Args:
            files: List of {"name", "path", "isDir", "width", "height"} dicts
            key: Sort key (uses current if None)
            ascending: Sort direction (uses current if None)
            
        Returns:
            New sorted list (does not modify original)
        """
        raise NotImplementedError("TODO: Implement - Sort files, folders first if enabled")
    
    @Slot(SortKey)
    def setKey(self, key: SortKey):
        """Change the sort key."""
        raise NotImplementedError("TODO: Implement - Update key, emit sortChanged")
    
    @Slot(bool)
    def setAscending(self, ascending: bool):
        """Change sort direction."""
        raise NotImplementedError("TODO: Implement - Update direction, emit sortChanged")
    
    @Slot(bool)
    def setFoldersFirst(self, enabled: bool):
        """Toggle folders-first behavior."""
        self._folders_first = enabled
    
    @Slot(result=SortKey)
    def currentKey(self) -> SortKey:
        """Get current sort key."""
        return self._current_key
    
    @Slot(result=bool)
    def isAscending(self) -> bool:
        """Get current sort direction."""
        return self._ascending
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _get_sort_value(self, file_dict: dict, key: SortKey):
        """
        Extract the sortable value from a file dict.
        
        For DATE_MODIFIED/SIZE, may need to stat the file (slow!).
        Consider caching or reading during scan.
        """
        raise NotImplementedError("TODO: Implement - Return sortable value for key")
