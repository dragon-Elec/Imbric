"""
GIO Q-Thread Orchestrator ASync Tasks (QTOAST) for PySide6/Qt.

A high-precision utility designed to wrap synchronous GNOME/GIO operations 
into the PySide6/Qt threading ecosystem (QThreadPool).

Key Architectural Features:
1. GIO-to-Qt Bridge: Safe signal-based result routing between C-based GIO and Qt.
2. Priority Orchestration: Lowest-integer-first priority queueing.
3. Batch Lifecycle: Atomic tracking of task groups with a 'batch_done' signal.
4. Progress Relaying: Mid-task feedback for long-running I/O.
"""

import inspect
import threading
import heapq
import itertools
from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QMutex, QMutexLocker

class GioTask(QRunnable):
    """
    A generic QRunnable representing a single unit of background work.
    Wraps GIO logic into the Qt Thread Pool.
    """
    def __init__(
        self,
        task_id: str,
        func: Callable[..., Any],
        on_complete_callback: Callable[[str, Any, str | None, bool], None],
        on_progress_callback: Callable[[str, int, int], None],
        cancel_event: threading.Event,
        inject_cancel: bool,
        *args: Any,
        **kwargs: Any
    ):
        super().__init__()
        self.task_id = task_id
        self.func = func
        self.on_complete = on_complete_callback
        self.on_progress = on_progress_callback
        self.args = args
        self.kwargs = kwargs.copy()
        self.cancel_event = cancel_event
        self.inject_cancel = inject_cancel
        self.setAutoDelete(True)

        # Cache signature introspection once
        try:
            sig = inspect.signature(func)
            params = sig.parameters
            self._accepts_var_kw = any(p.kind == p.VAR_KEYWORD for p in params.values())
            self._named_params = set(params.keys())
        except (ValueError, TypeError):
            # Builtins or C-extensions may not be introspectable
            self._accepts_var_kw = False
            self._named_params = set()

    def _safe_inject(self) -> None:
        """Only inject kwargs the target function can actually accept."""
        if self.inject_cancel and self._can_accept('cancel_event'):
            self.kwargs['cancel_event'] = self.cancel_event
        if self._can_accept('report_progress'):
            self.kwargs['report_progress'] = lambda current, total: self.on_progress(self.task_id, current, total)

    def _can_accept(self, name: str) -> bool:
        return self._accepts_var_kw or name in self._named_params

    def run(self) -> None:
        """Executes the task in a background thread."""
        if self.cancel_event.is_set():
            self.on_complete(self.task_id, None, None, True)
            return

        # Introspect: only inject kwargs the function can actually accept
        self._safe_inject()

        try:
            res = self.func(*self.args, **self.kwargs)
            if not self.cancel_event.is_set():
                self.on_complete(self.task_id, res, None, False)
            else:
                self.on_complete(self.task_id, None, None, True)
        except Exception as e:
            if not self.cancel_event.is_set():
                self.on_complete(self.task_id, None, str(e), False)
            else:
                self.on_complete(self.task_id, None, None, True)


class GioWorkerPool(QObject):
    """
    The Orchestrator. Manages thread pools, priorities, and batch states.
    """
    # Result Signals
    resultReady = Signal(str, object)      # (task_id, result_data)
    errorOccurred = Signal(str, str)       # (task_id, error_message)
    progressUpdated = Signal(str, int, int) # (task_id, current, total)
    
    # Batch Lifecycle Signals
    allTasksDone = Signal(str)             # (batch_id) emitted when batch finishes

    def __init__(self, max_concurrent: int = 4, parent: QObject | None = None):
        super().__init__(parent)
        self.max_concurrent = max_concurrent
        
        # Priority Queue: (priority, counter, task_data)
        self._queue: list[tuple[int, int, Any]] = []
        self._counter = itertools.count()
        
        # Batch Tracking: {batch_id: remaining_tasks}
        self._pending_batches: dict[str, int] = {}
        # Success/Failure tracking for batch reporting
        self._batch_stats: dict[str, dict[str, int]] = {}
        # Per-Batch Abort Switches (Fixes Zombie Tasks)
        self._batch_events: dict[str, threading.Event] = {}
        
        self._active_count = 0
        self._mutex = QMutex()
        self._pool = QThreadPool.globalInstance()
        self._global_cancel = threading.Event()

    def enqueue(
        self,
        task_id: str,
        func: Callable[..., Any],
        batch_id: str | None = None,
        priority: int = 50,
        inject_cancel: bool = False,
        *args: Any,
        **kwargs: Any
    ) -> None:
        """Submit a single task for orchestration."""
        with QMutexLocker(self._mutex):
            self._register_batch(batch_id)
            self._enqueue_locked(task_id, func, batch_id, priority, inject_cancel, args, kwargs)
        self._process_queue()

    def enqueue_batch(
        self,
        tasks: Iterable[tuple[str, Callable[..., Any], tuple, dict]],
        batch_id: str,
        priority: int = 50,
        inject_cancel: bool = False
    ) -> None:
        """Submit a collection of tasks atomically."""
        with QMutexLocker(self._mutex):
            self._register_batch(batch_id)
            for task_id, func, args, kwargs in tasks:
                self._enqueue_locked(task_id, func, batch_id, priority, inject_cancel, args, kwargs)
        self._process_queue()

    def _enqueue_locked(self, task_id, func, batch_id, priority, inject_cancel, args, kwargs):
        task_data = (task_id, func, batch_id, inject_cancel, args, kwargs)
        heapq.heappush(self._queue, (priority, next(self._counter), task_data))
        if batch_id:
            self._pending_batches[batch_id] += 1
            self._batch_stats[batch_id]['total'] += 1

    def _register_batch(self, batch_id: str | None):
        if batch_id and batch_id not in self._pending_batches:
            self._pending_batches[batch_id] = 0
            self._batch_stats[batch_id] = {'total': 0, 'done': 0, 'error': 0}
            self._batch_events[batch_id] = threading.Event()

    def clear(self, batch_id: str | None = None) -> None:
        """Cancel tasks. If batch_id is provided, only cancel that specific batch."""
        with QMutexLocker(self._mutex):
            if batch_id:
                # Abort Active Tasks Instantly
                if batch_id in self._batch_events:
                    self._batch_events[batch_id].set()
                    del self._batch_events[batch_id]
                
                # Filter queue to remove batch tasks
                self._queue = [(p, c, d) for p, c, d in self._queue if d[2] != batch_id]
                heapq.heapify(self._queue)
                if batch_id in self._pending_batches:
                    del self._pending_batches[batch_id]
                    if batch_id in self._batch_stats: del self._batch_stats[batch_id]
            else:
                self._queue.clear()
                self._pending_batches.clear()
                self._batch_stats.clear()
                
                # Abort all global and batch events
                for evt in self._batch_events.values(): evt.set()
                self._batch_events.clear()
                self._global_cancel.set()
                self._global_cancel = threading.Event()

    def forget_batch(self, batch_id: str) -> None:
        """Clear all tracking data for a completed batch to free memory."""
        with QMutexLocker(self._mutex):
            if batch_id in self._pending_batches: del self._pending_batches[batch_id]
            if batch_id in self._batch_stats: del self._batch_stats[batch_id]
            if batch_id in self._batch_events: del self._batch_events[batch_id]

    def get_batch_stats(self, batch_id: str) -> dict:
        """Get the current progress of a specific batch."""
        with QMutexLocker(self._mutex):
            return self._batch_stats.get(batch_id, {'total': 0, 'done': 0, 'error': 0})

    def _process_queue(self) -> None:
        with QMutexLocker(self._mutex):
            while self._queue and self._active_count < self.max_concurrent:
                priority, _, task_data = heapq.heappop(self._queue)
                task_id, func, batch_id, inject_cancel, args, kwargs = task_data
                
                self._active_count += 1
                
                # Setup bridge callbacks
                on_end = lambda t_id, r, e, c, bid=batch_id: self._on_task_end(t_id, bid, r, e, c)
                on_prog = lambda t_id, c_p, t_p: self.progressUpdated.emit(t_id, c_p, t_p)
                
                # Determine specific abort switch
                cancel_evt = self._batch_events.get(batch_id, self._global_cancel) if batch_id else self._global_cancel
                
                runnable = GioTask(
                    task_id, func, on_end, on_prog, cancel_evt, inject_cancel, *args, **kwargs
                )
                
                # Align Python priority (0=High) with Qt priority (High wins)
                self._pool.start(runnable, -priority)

    def _on_task_end(self, task_id: str, batch_id: str | None, result: Any, error: str | None, cancelled: bool):
        batch_done_signal = False
        
        with QMutexLocker(self._mutex):
            self._active_count -= 1
            
            if not cancelled:
                if batch_id and batch_id in self._batch_stats:
                    if error is not None:
                        self._batch_stats[batch_id]['error'] += 1
                    else:
                        self._batch_stats[batch_id]['done'] += 1
                
                if error is None:
                    self.resultReady.emit(task_id, result)
                else:
                    self.errorOccurred.emit(task_id, error)
            
            if batch_id and batch_id in self._pending_batches:
                self._pending_batches[batch_id] -= 1
                if self._pending_batches[batch_id] <= 0:
                    del self._pending_batches[batch_id]
                    # Clean up event switch for memory
                    if batch_id in self._batch_events:
                        del self._batch_events[batch_id]
                    batch_done_signal = True
        
        if batch_done_signal:
            self.allTasksDone.emit(batch_id)
            
        self._process_queue()
