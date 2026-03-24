"""
Search Engines - Abstract base class and concrete implementations.
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
    def search(
        self, directory: str, pattern: str, recursive: bool = True
    ) -> Iterator[str]:
        """Search for files matching pattern."""
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
    """Search engine using `fd` (fdfind) for fast file discovery."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._fd_binary = self._find_fd_binary()

    @staticmethod
    def _find_fd_binary() -> Optional[str]:
        for name in ("fd", "fdfind"):
            path = shutil.which(name)
            if path:
                return path
        return None

    @staticmethod
    def is_available() -> bool:
        return FdSearchEngine._find_fd_binary() is not None

    @property
    def name(self) -> str:
        return "fd"

    def search(
        self, directory: str, pattern: str, recursive: bool = True
    ) -> Iterator[str]:
        if not self._fd_binary:
            return

        cmd = [
            self._fd_binary,
            "--absolute-path",
            "--hidden",
            "--no-ignore",
        ]

        if not recursive:
            cmd.extend(["--max-depth", "1"])

        cmd.append(pattern if pattern else ".")
        cmd.append(directory)

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            for line in self._process.stdout:
                path = line.rstrip("\n")
                if path:
                    yield path

        except Exception:
            pass
        finally:
            self._cleanup()

    def stop(self):
        if self._process:
            self._process.terminate()
            self._cleanup()

    def _cleanup(self):
        if self._process:
            try:
                self._process.stdout.close()
                self._process.wait(timeout=1)
            except Exception:
                self._process.kill()
            self._process = None


class ScandirSearchEngine(SearchEngine):
    """Pure Python search engine using os.scandir."""

    def __init__(self):
        self._cancelled = False

    @property
    def name(self) -> str:
        return "scandir"

    def search(
        self, directory: str, pattern: str, recursive: bool = True
    ) -> Iterator[str]:
        self._cancelled = False

        if "*" not in pattern and "?" not in pattern:
            pattern = f"*{pattern}*"

        yield from self._walk(directory, pattern, recursive)

    def _walk(self, directory: str, pattern: str, recursive: bool) -> Iterator[str]:
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
                        continue
                    except OSError:
                        continue
        except PermissionError:
            pass
        except OSError:
            pass

    def stop(self):
        self._cancelled = True


def get_search_engine() -> SearchEngine:
    """Factory function to get the best available search engine."""
    if FdSearchEngine.is_available():
        return FdSearchEngine()
    return ScandirSearchEngine()
