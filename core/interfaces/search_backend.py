"""
SearchBackend ABC - Contract for live file search.
Backend streams results via signals. UI just renders.
"""

from abc import ABCMeta, ABC, abstractmethod
from PySide6.QtCore import QObject, Signal, Slot


class ABCQObjectMeta(ABCMeta, type(QObject)):
    """Combined metaclass for classes that inherit from both ABC and QObject."""

    pass


class SearchBackend(ABC, QObject, metaclass=ABCQObjectMeta):
    """Contract for live file search.

    Signals (live, 50-100ms debounce max):
        resultsReady(list)   - list of FileInfo dicts
        searchFinished(str)  - session_id
        searchError(str)     - error message
    """

    resultsReady = Signal(list)
    searchFinished = Signal(str)
    searchError = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @abstractmethod
    def search(self, query: str, path: str, mode: str, options: dict) -> None:
        """Start search. Backend picks the engine. Results stream live.

        Args:
            query: Search pattern or text.
            path: Directory to search in.
            mode: "filename" | "content" | "fuzzy"
            options: {recursive: bool, include_hidden: bool, ...}
        """
        pass

    @Slot()
    @abstractmethod
    def cancel(self) -> None:
        """Cancel ongoing search."""
        pass
