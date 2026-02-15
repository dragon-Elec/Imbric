"""
[DONE] Sorter — File Sorting Logic

Provides sorting capabilities for file lists (by name, date, size, type).
Used by RowBuilder before distributing files to rows.

Features:
- Multiple sort keys: Name, Date Modified, Size, Type (extension)
- Ascending/Descending toggle
- Folders-first option (enabled by default)
- Natural string sorting for names (handles "file2" before "file10")
- Stateful preferences with change notification

Usage:
    sorter = Sorter()
    sorted_files = sorter.sort(files)  # Uses current settings
    
    sorter.setKey(SortKey.DATE_MODIFIED)
    sorter.setAscending(False)  # Newest first
    sorted_files = sorter.sort(files)
"""

from PySide6.QtCore import QObject, Signal, Slot, Property
from enum import IntEnum
from typing import List, Optional
import re


class SortKey(IntEnum):
    """Available sort keys. IntEnum for easy QML interop."""
    NAME = 0            # Alphabetical by filename
    DATE_MODIFIED = 1   # By modification time
    SIZE = 2            # By file size
    TYPE = 3            # By file extension


class Sorter(QObject):
    """
    Sorts file lists by various criteria.
    
    Thread-safe: Sorting is a pure function on a copy of the data.
    Stateful: Remembers current key/direction for UI binding.
    """
    
    # Emitted when sort preference changes (for UI sync)
    sortChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = SortKey.NAME
        self._ascending = True
        self._folders_first = True
        
        # Compiled regex for natural sorting (split "file10" into ["file", 10])
        self._natural_re = re.compile(r'(\d+)')
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(list, result=list)
    def sort(self, files: List[dict], key: Optional[SortKey] = None, ascending: Optional[bool] = None) -> List[dict]:
        """
        Sort a list of file dicts.
        
        Args:
            files: List of {"name", "path", "isDir", "size", "dateModified", ...} dicts
            key: Sort key (uses current setting if None)
            ascending: Sort direction (uses current setting if None)
            
        Returns:
            New sorted list (does not modify original)
        """
        if not files:
            return []
        
        # Use current settings if not specified
        sort_key = key if key is not None else self._current_key
        is_asc = ascending if ascending is not None else self._ascending
        
        # Make a copy to avoid mutating the original
        result = list(files)
        
        # Define sort key function based on requested key
        def get_sort_value(item: dict):
            return self._get_sort_value(item, sort_key)
        
        # Sort with folders-first logic if enabled
        if self._folders_first:
            # Split into folders and files
            folders = [f for f in result if f.get("isDir", False)]
            regular = [f for f in result if not f.get("isDir", False)]
            
            # Sort each group
            folders.sort(key=get_sort_value, reverse=not is_asc)
            regular.sort(key=get_sort_value, reverse=not is_asc)
            
            # Combine: folders first
            return folders + regular
        else:
            # Sort everything together
            result.sort(key=get_sort_value, reverse=not is_asc)
            return result
    
    @Slot(int)
    def setKey(self, key: int) -> None:
        """Change the sort key. Accepts int for QML compatibility."""
        try:
            new_key = SortKey(key)
        except ValueError:
            return  # Invalid key, ignore
        
        if new_key != self._current_key:
            self._current_key = new_key
            self.sortChanged.emit()
    
    @Slot(bool)
    def setAscending(self, ascending: bool) -> None:
        """Change sort direction."""
        if ascending != self._ascending:
            self._ascending = ascending
            self.sortChanged.emit()
    
    @Slot(bool)
    def setFoldersFirst(self, enabled: bool) -> None:
        """Toggle folders-first behavior."""
        if enabled != self._folders_first:
            self._folders_first = enabled
            self.sortChanged.emit()
    
    @Slot(result=int)
    def currentKey(self) -> int:
        """Get current sort key as int (for QML)."""
        return int(self._current_key)
    
    @Slot(result=bool)
    def isAscending(self) -> bool:
        """Get current sort direction."""
        return self._ascending
    
    @Slot(result=bool)
    def isFoldersFirst(self) -> bool:
        """Get folders-first setting."""
        return self._folders_first
    
    # Qt Properties for QML binding
    key = Property(int, currentKey, setKey, notify=sortChanged)
    ascending = Property(bool, isAscending, setAscending, notify=sortChanged)
    foldersFirst = Property(bool, isFoldersFirst, setFoldersFirst, notify=sortChanged)
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _get_sort_value(self, file_dict: dict, key: SortKey):
        """
        Extract the sortable value from a file dict.
        
        Returns a tuple/value that can be compared with < operator.
        """
        if key == SortKey.NAME:
            # Natural sort: "file2" before "file10"
            name = file_dict.get("name", "").lower()
            return self._natural_sort_key(name)
        
        elif key == SortKey.DATE_MODIFIED:
            # Unix timestamp (larger = newer)
            return file_dict.get("dateModified", 0)
        
        elif key == SortKey.SIZE:
            return file_dict.get("size", 0)
        
        elif key == SortKey.TYPE:
            # Sort by extension, then by name for same extension
            name = file_dict.get("name", "")
            # Extract extension (lowercase, without dot)
            if '.' in name:
                ext = name.rsplit('.', 1)[-1].lower()
            else:
                ext = ""  # No extension sorts first
            return (ext, self._natural_sort_key(name.lower()))
        
        # Fallback
        return file_dict.get("name", "").lower()
    
    def _natural_sort_key(self, text: str) -> tuple:
        """
        Generate a sort key that handles embedded numbers naturally.
        
        "file2" < "file10" (unlike pure string comparison)
        
        Splits text into (str, int, str, int, ...) tuples for proper comparison.
        """
        parts = self._natural_re.split(text)
        result = []
        for part in parts:
            if part.isdigit():
                result.append(int(part))
            else:
                result.append(part)
        return tuple(result)
