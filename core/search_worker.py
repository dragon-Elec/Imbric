"""
[WIP] SearchWorker — Background Search with Batched Results

Runs search engine in a QThread, emits results in batches for responsive UI.
Supports progressive loading: paths first, then metadata on demand.

Usage:
    worker = SearchWorker()
    worker.resultsFound.connect(on_results)
    worker.start_search("/home", "photo")
"""

from PySide6.QtCore import QThread, Signal, Slot, QMutex, QMutexLocker
from typing import List, Optional
import os

from core.search import get_search_engine, SearchEngine


class SearchWorker(QThread):
    """
    Background worker for file search.
    
    Emits results in batches for responsive UI. The caller is responsible
    for fetching metadata (via Gio) for displayed items only.
    """
    
    # Signals
    resultsFound = Signal(list)     # Batch of paths (List[str])
    searchFinished = Signal(int)    # Total count found
    searchError = Signal(str)       # Error message
    searchStarted = Signal(str)     # Search directory
    
    # Configuration
    BATCH_SIZE = 50  # Emit results every N files
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: SearchEngine = get_search_engine()
        self._directory: str = ""
        self._pattern: str = ""
        self._recursive: bool = True
        self._cancelled: bool = False
        self._mutex = QMutex()
    
    @property
    def engine_name(self) -> str:
        """Name of the current search engine."""
        return self._engine.name
    
    @Slot(str, str, bool)
    def start_search(self, directory: str, pattern: str, recursive: bool = True):
        """
        Start a new search.
        
        If a search is already running, it will be cancelled first.
        
        Args:
            directory: Root directory to search.
            pattern: Search pattern (glob or substring).
            recursive: Search subdirectories.
        """
        # Cancel any running search
        if self.isRunning():
            self.cancel()
            self.wait(1000)  # Wait up to 1 second
        
        with QMutexLocker(self._mutex):
            self._directory = directory
            self._pattern = pattern
            self._recursive = recursive
            self._cancelled = False
        
        self.start()
    
    @Slot()
    def cancel(self):
        """Cancel the current search."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
        self._engine.stop()
    
    def run(self):
        """Thread main loop — performs the search."""
        with QMutexLocker(self._mutex):
            directory = self._directory
            pattern = self._pattern
            recursive = self._recursive
        
        if not directory or not os.path.isdir(directory):
            self.searchError.emit(f"Invalid directory: {directory}")
            return
        
        self.searchStarted.emit(directory)
        
        batch: List[str] = []
        total_count = 0
        
        try:
            for path in self._engine.search(directory, pattern, recursive):
                if self._is_cancelled():
                    break
                
                batch.append(path)
                total_count += 1
                
                if len(batch) >= self.BATCH_SIZE:
                    self.resultsFound.emit(batch.copy())
                    batch.clear()
            
            # Emit remaining results
            if batch and not self._is_cancelled():
                self.resultsFound.emit(batch)
                
        except Exception as e:
            self.searchError.emit(str(e))
            return
        
        self.searchFinished.emit(total_count)
    
    def _is_cancelled(self) -> bool:
        """Thread-safe check for cancellation."""
        with QMutexLocker(self._mutex):
            return self._cancelled


# ---------------------------------------------------------------------------
# CLI TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from PySide6.QtCore import QCoreApplication
    
    app = QCoreApplication(sys.argv)
    
    worker = SearchWorker()
    results_count = 0
    
    def on_results(paths):
        global results_count
        for p in paths[:5]:  # Show first 5 of each batch
            print(f"  {p}")
        results_count += len(paths)
        if len(paths) > 5:
            print(f"  ... (+{len(paths) - 5} more in batch)")
    
    def on_finished(total):
        print(f"\nSearch complete. Total: {total}")
        app.quit()
    
    def on_error(msg):
        print(f"Error: {msg}")
        app.quit()
    
    worker.resultsFound.connect(on_results)
    worker.searchFinished.connect(on_finished)
    worker.searchError.connect(on_error)
    
    search_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    pattern = sys.argv[2] if len(sys.argv) > 2 else ""
    
    print(f"Engine: {worker.engine_name}")
    print(f"Searching: {search_dir} for '{pattern}'\n")
    
    worker.start_search(search_dir, pattern)
    
    sys.exit(app.exec())
