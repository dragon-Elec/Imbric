"""
ItemCountWorker — Async Directory Item Counter

Background worker using QThreadPool to count items in directories
without blocking the main thread.

Features:
- Queue-based processing
- Uses os.scandir (C-optimized) for fast counting
- Cancellable via clear()
- Thread-safe signal emission
"""

import os
from collections import deque
from typing import Deque

from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QMutex, QMutexLocker


class CountTask(QRunnable):
    """
    A single counting task for one directory.
    
    Runs os.scandir in a thread pool thread.
    """
    
    def __init__(self, path: str, callback):
        super().__init__()
        self.path = path
        self.callback = callback
        self.setAutoDelete(True)
    
    def run(self):
        """Count items in directory using os.scandir."""
        count = 0
        try:
            with os.scandir(self.path) as entries:
                for _ in entries:
                    count += 1
        except (PermissionError, FileNotFoundError, OSError):
            # Return 0 on any error
            count = 0
        
        # Invoke callback (will be called from thread pool thread)
        self.callback(self.path, count)


class ItemCountWorker(QObject):
    """
    Manages a queue of directories to count.
    
    Signals:
        countReady(str, int): Emitted when a count is available (path, count).
    """
    
    countReady = Signal(str, int)
    
    # Max concurrent tasks (avoid flooding the pool)
    MAX_CONCURRENT = 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: Deque[str] = deque()
        self._active_count = 0
        self._mutex = QMutex()
        self._pool = QThreadPool.globalInstance()
    
    @Slot(str)
    def enqueue(self, path: str) -> None:
        """
        Add a directory path to the counting queue.
        
        If there's capacity, starts counting immediately.
        """
        with QMutexLocker(self._mutex):
            self._queue.append(path)
        
        self._process_queue()
    
    @Slot()
    def clear(self) -> None:
        """
        Clear all pending counts.
        
        Note: Already-running tasks cannot be cancelled.
        """
        with QMutexLocker(self._mutex):
            self._queue.clear()
    
    def _process_queue(self) -> None:
        """Start counting tasks up to MAX_CONCURRENT."""
        with QMutexLocker(self._mutex):
            while self._queue and self._active_count < self.MAX_CONCURRENT:
                path = self._queue.popleft()
                self._active_count += 1
                task = CountTask(path, self._on_task_done)
                self._pool.start(task)
    
    def _on_task_done(self, path: str, count: int) -> None:
        """
        Called by CountTask when counting finishes.
        
        This is called from a thread pool thread, so we use
        a queued signal connection (default for cross-thread).
        """
        with QMutexLocker(self._mutex):
            self._active_count -= 1
        
        # Emit signal (thread-safe, Qt handles queuing)
        self.countReady.emit(path, count)
        
        # Process more from queue
        self._process_queue()
