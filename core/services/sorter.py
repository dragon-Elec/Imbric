"""
File Sorting Logic.
Moved from core/sorter.py
"""

from PySide6.QtCore import QObject, Signal, Slot, Property
from enum import IntEnum
from typing import List, Optional
import re


class SortKey(IntEnum):
    NAME = 0
    DATE_MODIFIED = 1
    SIZE = 2
    TYPE = 3


class Sorter(QObject):
    """Sorts file lists by various criteria."""

    sortChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = SortKey.NAME
        self._ascending = True
        self._folders_first = True
        self._natural_re = re.compile(r"(\d+)")

    @Slot(list, result=list)
    def sort(
        self,
        files: List[dict],
        key: Optional[SortKey] = None,
        ascending: Optional[bool] = None,
    ) -> List[dict]:
        if not files:
            return []

        sort_key = key if key is not None else self._current_key
        is_asc = ascending if ascending is not None else self._ascending

        result = list(files)

        def get_sort_value(item: dict):
            return self._get_sort_value(item, sort_key)

        if self._folders_first:
            folders = [f for f in result if f.get("isDir", False)]
            regular = [f for f in result if not f.get("isDir", False)]

            folders.sort(key=get_sort_value, reverse=not is_asc)
            regular.sort(key=get_sort_value, reverse=not is_asc)

            return folders + regular
        else:
            result.sort(key=get_sort_value, reverse=not is_asc)
            return result

    @Slot(int)
    def setKey(self, key: int) -> None:
        try:
            new_key = SortKey(key)
        except ValueError:
            return

        if new_key != self._current_key:
            self._current_key = new_key
            self.sortChanged.emit()

    @Slot(bool)
    def setAscending(self, ascending: bool) -> None:
        if ascending != self._ascending:
            self._ascending = ascending
            self.sortChanged.emit()

    @Slot(bool)
    def setFoldersFirst(self, enabled: bool) -> None:
        if enabled != self._folders_first:
            self._folders_first = enabled
            self.sortChanged.emit()

    @Slot(result=int)
    def currentKey(self) -> int:
        return int(self._current_key)

    @Slot(result=bool)
    def isAscending(self) -> bool:
        return self._ascending

    @Slot(result=bool)
    def isFoldersFirst(self) -> bool:
        return self._folders_first

    key = Property(int, currentKey, setKey, notify=sortChanged)
    ascending = Property(bool, isAscending, setAscending, notify=sortChanged)
    foldersFirst = Property(bool, isFoldersFirst, setFoldersFirst, notify=sortChanged)

    def _get_sort_value(self, file_dict: dict, key: SortKey):
        if key == SortKey.NAME:
            name = file_dict.get("name", "").lower()
            return self._natural_sort_key(name)

        elif key == SortKey.DATE_MODIFIED:
            return file_dict.get("dateModified", 0)

        elif key == SortKey.SIZE:
            return file_dict.get("size", 0)

        elif key == SortKey.TYPE:
            name = file_dict.get("name", "")
            if "." in name:
                ext = name.rsplit(".", 1)[-1].lower()
            else:
                ext = ""
            return (ext, self._natural_sort_key(name.lower()))

        return file_dict.get("name", "").lower()

    def _natural_sort_key(self, text: str) -> tuple:
        parts = self._natural_re.split(text)
        result = []
        for part in parts:
            if part.isdigit():
                result.append(int(part))
            else:
                result.append(part)
        return tuple(result)
