# Imbric Core: Utilities
Role: Shared helper classes and low-level orchestrators for the core module.

## Maintenance Rules
- Thread Safety: Most utilities here are accessed from background workers. Use Mutexes where shared state exists.
- GIO First: Prefer GIO-based solutions for VFS compatibility.

## Atomic Notes (Architectural Truths)
- !Decision: [QThreadPool >> QThread] - Reason: Efficient reuse of worker threads for short-lived metadata tasks.
- !Rule: [Priority 0 = Urgent] - Reason: Follows GIO system priority (lowest is most urgent).

## Sub-Directory Index
- None

## Module Audits

### [FILE: [gio_qtoast.py](./gio_qtoast.py)] [DONE]
Role: GIO Q-Thread Orchestrator ASync Tasks (QTOAST).

/DNA/: [enqueue(task) -> heapq.heappush(priority) -> _process_queue() -> QThreadPool.start(GioTask) -> on_complete() -> em:resultReady -> if(batch_done) -> em:allTasksDone]

- SrcDeps: None
- SysDeps: threading, heapq, itertools, inspect, PySide6.QtCore (QObject, Signal, QRunnable, QThreadPool, QMutex)

API:
  - [GioWorkerPool](./gio_qtoast.py#L93)(QObject):
    - [enqueue](./gio_qtoast.py#L125)(task_id, func, priority, ...): Schedules a single task.
    - [enqueue_batch](./gio_qtoast.py#L141)(tasks, batch_id, ...): Schedules multiple tasks as a tracked unit.
    - [clear](./gio_qtoast.py#L168)(batch_id): Aborts pending and active tasks (via threading.Event).
!Caveat: `GioTask` automatically introspects `func` to inject `cancel_event` or `report_progress` if the signature accepts them.
