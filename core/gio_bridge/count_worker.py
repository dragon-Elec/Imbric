"""
ItemCountWorker — Async Directory Item Counter

Background worker using QThreadPool to count items in directories
without blocking the main thread.

Features:
- Queue-based processing
- Uses os.scandir (C-optimized) for fast counting
- Cooperative cancellation via threading.Event
- Thread-safe signal emission
"""

import os
import threading
from collections import deque
from typing import Deque

from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QMutex, QMutexLocker


class CountSignals(QObject):
    """Signals for CountTask."""
    result = Signal(str, int)

class CountTask(QRunnable):
    """
    A single counting task for one directory.
    Runs os.scandir in a thread pool thread.
    Supports cooperative cancellation via threading.Event.
    """
    
    def __init__(self, path: str, cancel_event: threading.Event):
        super().__init__()
        self.path = path
        self._cancel = cancel_event
        self.signals = CountSignals()
        self.setAutoDelete(True)
    
    def run(self):
        """Count items in directory using os.scandir."""
        count = 0
        try:
            with os.scandir(self.path) as entries:
                for _ in entries:
                    # [FIX] Check cancellation flag every iteration
                    if self._cancel.is_set():
                        return  # Abort early, don't emit
                    count += 1
        except (PermissionError, FileNotFoundError, OSError):
            # Return 0 on any error
            count = 0
        
        # Only emit if not cancelled
        if not self._cancel.is_set():
            self.signals.result.emit(self.path, count)

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
        # [FIX] Shared cancellation token for cooperative thread abort
        self._cancel_event = threading.Event()
    
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
        Clear all pending counts and signal running tasks to abort.
        """
        with QMutexLocker(self._mutex):
            self._queue.clear()
            # [FIX] Signal all running tasks to abort
            self._cancel_event.set()
            # Reset for next scan session
            self._cancel_event = threading.Event()
    
    def _process_queue(self) -> None:
        """Start counting tasks up to MAX_CONCURRENT."""
        with QMutexLocker(self._mutex):
            while self._queue and self._active_count < self.MAX_CONCURRENT:
                path = self._queue.popleft()
                self._active_count += 1
                
                # [FIX] Pass cancel_event for cooperative cancellation
                task = CountTask(path, self._cancel_event)
                
                # Connect signal to slot (QueuedConnection is automatic across threads)
                task.signals.result.connect(self._on_task_done)
                
                self._pool.start(task)
    
    @Slot(str, int)
    def _on_task_done(self, path: str, count: int) -> None:
        """
        Called via Signal when counting finishes.
        """
        with QMutexLocker(self._mutex):
            self._active_count -= 1
        
        # Forward the result
        self.countReady.emit(path, count)
        
        # Process more from queue
        self._process_queue()

