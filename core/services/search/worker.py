"""
Search Worker - Background search with batched results.
Moved from core/search_worker.py
"""

from PySide6.QtCore import QThread, Signal, Slot, QMutex, QMutexLocker
from typing import List
import os

from core.services.search.engines import get_search_engine, SearchEngine
from core.registry import BackendRegistry


class SearchWorker(QThread):
    """Background worker for file search."""

    resultsFound = Signal(list)
    searchFinished = Signal(int)
    searchError = Signal(str)
    searchStarted = Signal(str)

    BATCH_SIZE = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: SearchEngine = get_search_engine()
        self._directory: str = ""
        self._pattern: str = ""
        self._recursive: bool = True
        self._cancelled: bool = False
        self._mutex = QMutex()
        self._registry: BackendRegistry | None = None

    def setRegistry(self, registry: BackendRegistry):
        self._registry = registry

    @property
    def engine_name(self) -> str:
        return self._engine.name

    @Slot(str, str, bool)
    def start_search(self, directory: str, pattern: str, recursive: bool = True):
        if self.isRunning():
            self.cancel()
            self.wait(1000)

        with QMutexLocker(self._mutex):
            self._directory = directory
            self._pattern = pattern
            self._recursive = recursive
            self._cancelled = False

        self.start()

    @Slot()
    def cancel(self):
        with QMutexLocker(self._mutex):
            self._cancelled = True
        self._engine.stop()

    def run(self):
        with QMutexLocker(self._mutex):
            search_uri = self._directory
            pattern = self._pattern
            recursive = self._recursive

        if not self._registry:
            self.searchError.emit("Backend registry not configured for SearchWorker.")
            return

        backend = self._registry.get_io(search_uri)

        if not backend.query_exists(search_uri):
            self.searchError.emit(f"Invalid location: {search_uri}")
            return

        local_search_path = backend.get_local_path(search_uri)

        if not local_search_path or not os.path.isdir(local_search_path):
            error_msg = f"Search is not supported on this location ('{search_uri}'). "
            if not local_search_path:
                error_msg += (
                    "Try opening this folder in the view first to trigger a FUSE mount."
                )
            self.searchError.emit(error_msg)
            return

        self.searchStarted.emit(search_uri)

        batch: List[str] = []
        total_count = 0

        try:
            for path in self._engine.search(local_search_path, pattern, recursive):
                if self._is_cancelled():
                    break

                batch.append(path)
                total_count += 1

                if len(batch) >= self.BATCH_SIZE:
                    self.resultsFound.emit(batch.copy())
                    batch.clear()

            if batch and not self._is_cancelled():
                self.resultsFound.emit(batch)

        except Exception as e:
            self.searchError.emit(str(e))
            return

        self.searchFinished.emit(total_count)

    def _is_cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancelled
