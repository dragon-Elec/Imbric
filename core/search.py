"""
[STUB] Search — File Search/Filter Logic

Provides file search capabilities (recursive search, filename filter).
Can be used for both in-view filtering and deep directory search.

Usage:
    search = FileSearch()
    search.resultsFound.connect(on_results)
    search.search("/home/user", "*.jpg", recursive=True)
    
Integration:
    - MainWindow provides Ctrl+F search bar
    - Results shown in main view or separate search results panel
    - Filter mode for non-recursive in-current-dir filtering
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import List
import fnmatch


class FileSearch(QObject):
    """
    Async file search using Gio.
    Emits results in batches for responsive UI.
    """
    
    # Signals
    resultsFound = Signal(list)   # Batch of matching file dicts
    searchFinished = Signal(int)  # Total count found
    searchError = Signal(str)     # Error message
    searchProgress = Signal(int)  # Files scanned so far
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancellable = None
        self._pattern = ""
        self._case_sensitive = False
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(str, str, bool)
    def search(self, directory: str, pattern: str, recursive: bool = True):
        """
        Start an async file search.
        
        Args:
            directory: Root directory to search
            pattern: Glob pattern (e.g., "*.jpg", "photo*")
            recursive: Search subdirectories
        """
        raise NotImplementedError("TODO: Implement - Async Gio enumeration with pattern matching")
    
    @Slot(list, str, result=list)
    def filter(self, files: List[dict], pattern: str) -> List[dict]:
        """
        Filter an existing file list (synchronous, for quick filtering).
        
        Args:
            files: List of file dicts from scanner
            pattern: Glob pattern to match against name
            
        Returns:
            Filtered list (subset of input)
        """
        raise NotImplementedError("TODO: Implement - fnmatch.filter on file names")
    
    @Slot()
    def cancel(self):
        """Cancel ongoing search."""
        if self._cancellable:
            self._cancellable.cancel()
    
    @Slot(bool)
    def setCaseSensitive(self, enabled: bool):
        """Toggle case-sensitive matching."""
        self._case_sensitive = enabled
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _matches(self, filename: str, pattern: str) -> bool:
        """Check if filename matches the glob pattern."""
        if self._case_sensitive:
            return fnmatch.fnmatch(filename, pattern)
        return fnmatch.fnmatch(filename.lower(), pattern.lower())
