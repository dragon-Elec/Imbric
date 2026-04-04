"""
MetadataWorkers ABC - Contracts for async metadata extraction.
"""

from PySide6.QtCore import QObject, Signal


class ItemCountWorkerBackend(QObject):
    """Contract for async directory item counting."""

    countReady = Signal(str, int)  # path, count

    def __init__(self, parent=None):
        super().__init__(parent)

    def enqueue(self, uri: str, path: str) -> None:
        """Enqueue a path to be counted."""
        pass

    def clear(self) -> None:
        """Clear the pending queue."""
        pass


class DimensionWorkerBackend(QObject):
    """Contract for async image dimension extraction."""

    dimensionsReady = Signal(str, int, int)  # identifier, width, height

    def __init__(self, parent=None):
        super().__init__(parent)

    def enqueue(self, uri: str, path: str) -> None:
        """Enqueue an image to extract dimensions."""
        pass

    def clear(self) -> None:
        """Clear the pending queue."""
        pass
