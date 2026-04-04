Identity: core/threading — GIO-to-Qt threading bridge. Wraps synchronous GIO callables into QThreadPool with priority queueing, batch tracking, and cancellation.

!Rule: [Signal only, never direct call from worker] - Reason: AsyncTask runs on QThreadPool threads; direct Qt UI mutation = crash. All results surface via resultReady / errorOccurred signals.
!Decision: [heapq priority queue > QThreadPool priority] - Reason: QThreadPool priority is coarse; heapq gives integer-precise ordering per task within the pool slot window.
!Pattern: [batch_id groups tasks] - Reason: `allTasksDone` fires when pending_batches[batch_id] reaches 0, enabling atomic "all done" notification for thumbnail/scan batches.

---

### [FILE: worker_pool.py] [DONE]
Role: Priority-aware QRunnable wrapper and batch-tracking QObject for GIO operations.

/DNA/: `enqueue(task_id, func, ...)` -> [push heapq, ++pending_batches] -> `_process_queue()` -> if active < max: `AsyncTask(func).run()` -> [success: em:resultReady | error: em:errorOccurred] -> --active -> if()batch_done: em:allTasksDone -> `_process_queue()`

- SysDeps: PySide6{QtCore}, threading, heapq, itertools, collections.abc, typing

API:
  - AsyncTask(QRunnable):
    - run(): injects cancel_event/report_progress kwargs via _safe_inject -> calls func -> on_complete callback (not signal)
    !Caveat: Uses `inspect.signature` to detect if func accepts `cancel_event`/`report_progress`; wrapped C-extension funcs may fail signature inspection silently.

  - AsyncWorkerPool(QObject):
    Signals: resultReady(task_id, result), errorOccurred(task_id, error), progressUpdated(task_id, current, total), allTasksDone(batch_id)
    - enqueue(task_id, func, batch_id=None, priority=50, inject_cancel=False, *args, **kwargs) -> None
    - enqueue_batch(tasks, batch_id, priority=50, inject_cancel=False) -> None
    - clear(batch_id=None) -> None: clears queue (all or per-batch) + signals batch event
    - forget_batch(batch_id) -> None: removes tracking state without cancelling running tasks
    - get_batch_stats(batch_id) -> {total, done, error}

!Caveat: `WorkerPool` is a backwards-compat alias for `AsyncWorkerPool`.
!Caveat: Cancelled tasks (cancel_event.is_set()) do NOT emit resultReady or errorOccurred; they are silently dropped.
