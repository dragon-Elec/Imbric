"""
[WIP] Search — File Search Engines

Provides multiple search backends with a unified interface:
- FdSearchEngine: Fast search via `fd` (fdfind) subprocess.
- ScandirSearchEngine: Pure Python fallback using os.scandir.

Usage:
    engine = get_search_engine()
    for path in engine.search("/home/user", "photo"):
        print(path)
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional
import os
import shutil
import subprocess
import fnmatch


class SearchEngine(ABC):
    """
    Abstract base class for search engines.
    
    All engines yield paths as strings. Metadata is fetched lazily by the caller.
    """
    
    @abstractmethod
    def search(self, directory: str, pattern: str, recursive: bool = True) -> Iterator[str]:
        """
        Search for files matching pattern.
        
        Args:
            directory: Root directory to search.
            pattern: Search pattern (glob or substring depending on engine).
            recursive: Search subdirectories.
            
        Yields:
            Absolute file paths matching the pattern.
        """
        pass
    
    @abstractmethod
    def stop(self):
        """Stop the current search."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the engine."""
        pass


class FdSearchEngine(SearchEngine):
    """
    Search engine using `fd` (fdfind) for fast file discovery.
    
    fd is a Rust-based tool that's 10-50x faster than find/os.walk.
    Falls back gracefully if fd is not installed.
    """
    
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._fd_binary = self._find_fd_binary()
    
    @staticmethod
    def _find_fd_binary() -> Optional[str]:
        """Find the fd binary (named 'fd' or 'fdfind' on Ubuntu)."""
        for name in ("fd", "fdfind"):
            path = shutil.which(name)
            if path:
                return path
        return None
    
    @staticmethod
    def is_available() -> bool:
        """Check if fd is installed on the system."""
        return FdSearchEngine._find_fd_binary() is not None
    
    @property
    def name(self) -> str:
        return "fd"
    
    def search(self, directory: str, pattern: str, recursive: bool = True) -> Iterator[str]:
        """
        Search using fd subprocess.
        
        Args:
            directory: Root directory to search.
            pattern: Regex pattern for fd (use --glob for glob patterns).
            recursive: If False, limits to --max-depth 1.
            
        Yields:
            Absolute file paths.
        """
        if not self._fd_binary:
            return
        
        # Build fd command
        cmd = [
            self._fd_binary,
            "--absolute-path",  # Return absolute paths
            "--hidden",         # Include hidden files
            "--no-ignore",      # Don't respect .gitignore (search everything)
        ]
        
        if not recursive:
            cmd.extend(["--max-depth", "1"])
        
        # Add pattern (empty string matches all)
        cmd.append(pattern if pattern else ".")
        cmd.append(directory)
        
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # Line-buffered for streaming
            )
            
            for line in self._process.stdout:
                path = line.rstrip('\n')
                if path:
                    yield path
                    
        except Exception:
            pass  # Silently fail, caller can fallback
        finally:
            self._cleanup()
    
    def stop(self):
        """Terminate the fd subprocess."""
        if self._process:
            self._process.terminate()
            self._cleanup()
    
    def _cleanup(self):
        """Clean up subprocess resources."""
        if self._process:
            try:
                self._process.stdout.close()
                self._process.wait(timeout=1)
            except Exception:
                self._process.kill()
            self._process = None


class ScandirSearchEngine(SearchEngine):
    """
    Pure Python search engine using os.scandir.
    
    Slower than fd but works everywhere (Linux, Android, Windows).
    """
    
    def __init__(self):
        self._cancelled = False
    
    @property
    def name(self) -> str:
        return "scandir"
    
    def search(self, directory: str, pattern: str, recursive: bool = True) -> Iterator[str]:
        """
        Search using os.scandir recursively.
        
        Args:
            directory: Root directory to search.
            pattern: Glob pattern (e.g., "*.jpg", "photo*").
            recursive: Search subdirectories.
            
        Yields:
            Absolute file paths matching the pattern.
        """
        self._cancelled = False
        
        # Convert pattern to work with fnmatch
        # If pattern doesn't have wildcards, treat as substring search
        if '*' not in pattern and '?' not in pattern:
            pattern = f"*{pattern}*"
        
        yield from self._walk(directory, pattern, recursive)
    
    def _walk(self, directory: str, pattern: str, recursive: bool) -> Iterator[str]:
        """Recursive directory walker with pattern matching."""
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if self._cancelled:
                        return
                    
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                yield from self._walk(entry.path, pattern, recursive)
                        else:
                            if fnmatch.fnmatch(entry.name.lower(), pattern.lower()):
                                yield entry.path
                    except PermissionError:
                        continue  # Skip inaccessible files
                    except OSError:
                        continue  # Skip broken symlinks, etc.
        except PermissionError:
            pass  # Skip inaccessible directories
        except OSError:
            pass
    
    def stop(self):
        """Signal the search to stop."""
        self._cancelled = True


def get_search_engine() -> SearchEngine:
    """
    Factory function to get the best available search engine.
    
    Returns:
        FdSearchEngine if fd is installed, otherwise ScandirSearchEngine.
    """
    if FdSearchEngine.is_available():
        return FdSearchEngine()
    return ScandirSearchEngine()


# ---------------------------------------------------------------------------
# LEGACY API (for backwards compatibility with existing stub)
# ---------------------------------------------------------------------------

from PySide6.QtCore import QObject, Signal, Slot
from typing import List


class FileSearch(QObject):
    """
    Qt-based async file search (legacy API).
    
    Wraps SearchEngine for Qt signal/slot integration.
    For new code, prefer using SearchWorker directly.
    """
    
    # Signals
    resultsFound = Signal(list)   # Batch of paths
    searchFinished = Signal(int)  # Total count found
    searchError = Signal(str)     # Error message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = get_search_engine()
        self._case_sensitive = False
    
    @Slot(str, str, bool)
    def search(self, directory: str, pattern: str, recursive: bool = True):
        """
        Start a search (blocking, for simple use cases).
        
        For non-blocking search, use SearchWorker instead.
        """
        results = []
        try:
            for path in self._engine.search(directory, pattern, recursive):
                results.append(path)
                if len(results) >= 50:
                    self.resultsFound.emit(results.copy())
                    results.clear()
            
            if results:
                self.resultsFound.emit(results)
                
        except Exception as e:
            self.searchError.emit(str(e))
        
        self.searchFinished.emit(len(results))
    
    @Slot(list, str, result=list)
    def filter(self, files: List[dict], pattern: str) -> List[dict]:
        """Filter an existing file list (synchronous)."""
        if not pattern:
            return files
        
        pattern_lower = pattern.lower()
        return [f for f in files if pattern_lower in f.get("name", "").lower()]
    
    @Slot()
    def cancel(self):
        """Cancel ongoing search."""
        self._engine.stop()
    
    @Slot(bool)
    def setCaseSensitive(self, enabled: bool):
        """Toggle case-sensitive matching."""
        self._case_sensitive = enabled


# ---------------------------------------------------------------------------
# CLI TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    engine = get_search_engine()
    print(f"Using engine: {engine.name}")
    
    search_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    pattern = sys.argv[2] if len(sys.argv) > 2 else ""
    
    print(f"Searching: {search_dir} for '{pattern}'")
    
    count = 0
    for path in engine.search(search_dir, pattern):
        print(path)
        count += 1
        if count >= 20:
            print(f"... (showing first 20 of many)")
            break
    
    print(f"\nTotal shown: {count}")
