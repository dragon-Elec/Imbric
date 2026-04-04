Identity: /Imbric/core - Central business logic, VFS abstraction (Gio), and transaction orchestration.
Rules:
- Non-Blocking: Never perform Gio I/O in main thread. Use QThreadPool.
- Gio Priority: Use Gio (VFS) for all operations (MTP/network support). Avoid os except for local scandir.
- Atomic Renames: Implement atomic retry-loops to prevent collisions during creation.
- Error Handling: Use PARTIAL:N status strings for batch failures; do not halt on first error.

!Decision: [Gio >> os.stat/shutil] - Reason: VFS transparency. Python `os` fails on MTP and GDrive mounts. Gio is mandatory for Linux Desktop parity.
!Rule: [Signalling > Direct Call] - Reason: Thread-safety. Background workers MUST emit signals; never mutate UI objects directly.

Index:
- backends/: Concrete I/O backends (GIO).
- interfaces/: Abstract contracts for backends/services.
- managers/: High-level controllers (FileOperations).
- models/: Pure DTO structs (FileInfo, FileJob).
- services/: Stateless logic (Sorter, Validator, Search).
- threading/: AsyncWorkerPool (QTOAST) bridge.
- utils/: Shared path and formatting helpers.

### [FILE: registry.py] [USABLE]
Role: BackendRegistry — URI-scheme-to-backend dispatcher for agnostic I/O.

/DNA/: [register_io(scheme, backend) -> _io_backends[scheme]=backend] -> [get_io(path) -> if("://" in path) => _io_backends[scheme] | else: _default_io]

- SrcDeps: core.interfaces{IOBackend, ScannerBackend, ThumbnailProviderBackend, MetadataProvider}
- SysDeps: (none)

API:
  - BackendRegistry:
    - register_io(scheme, backend) / set_default_io(backend) / get_io(path_or_uri) => IOBackend | None
    - get_io_id(path_or_uri) -> str: returns the scheme key or "default".
    - register_scanner(scheme, backend) / set_default_scanner(backend) / get_scanner(path_or_uri) => ScannerBackend | None
    - register_thumbnail(backend) / get_thumbnail(mime_type) => ThumbnailProviderBackend | None
    - set_metadata_provider(provider) / get_metadata() => MetadataProvider | None
    - get_io_signals() => FileOperationSignals | None: retrieves signals from current default_io.
!Caveat: `get_io_signals` returns the internal `_signals` handle from the default backend.

### [FILE: transaction.py] [USABLE]
Role: Data models for batch operation tracking and state serialization.

/DNA/: [Transaction(dataclass) -> add_operation(op) -> ops.append(op) ++ total_ops] -> [find_operation(job_id) => TransactionOperation]

- SrcDeps: None
- SysDeps: dataclasses, enum, time

API:
  - TransactionStatus(Enum): PENDING, RUNNING, COMPLETED, FAILED, CANCELLED.
  - TransactionOperation(dataclass): op_type, src, dest, result_path, job_id, status, error.
  - Transaction(dataclass): id, description, ops, total_ops, completed_ops, status, is_committed.
    - add_operation(op: TransactionOperation): registers atomic unit.
    - find_operation(job_id) => TransactionOperation | None: retrieves operation by its low-level ID.
    - update_status(job_id, status, error): updates status of a specific operation.
    - get_progress() => float: percentage (completed/total).

### [FILE: transaction_manager.py] [USABLE]
Role: Central CNS; orchestrates batch lifecycle and tracks high-level progress.

/DNA/: [batchTransfer(sources, dest) -> startTransaction(tid) -> call:file_ops.assessBatch() -> wait assessmentReady -> call:file_ops.transfer_batch() -> onOperationFinished() -> em:transactionProgress]
/DNA/: [onOperationError() -> if(conflict) -> _pending_conflicts[job_id]=data -> em:conflictDetected -> wait -> resolveConflict() -> execute resolution]

- SrcDeps: core.transaction, core.utils.path_ops
- SysDeps: PySide6{QtCore}, uuid, typing

API:
  - startTransaction(description) => tid
  - addOperation(tid, op_type, src, dest, job_id) -> None
  - batchTransfer(sources, dest_dir, mode, resolver) -> None: high-level entry point.
  - setFileOperations(file_ops) / setValidator(validator) / setTrashManager(tm): dependency injection.
  - resolveConflict(job_id, resolution, new_name) -> None: executes resolution via file_ops.
  - commitTransaction(tid) -> None: marks population done, closes if all ops finished.
  - onBatchAssessmentReady(tid, valid, conflicts) / onOperationStarted(job_id, type, path) / onOperationProgress(job_id, current, total): signal handlers.
  Signals: transactionStarted, transactionFinished, transactionProgress, transactionUpdate, historyCommitted, conflictDetected, conflictResolved, jobCompleted, operationFailed.
!Caveat: `setTrashManager` is a legacy stub (no-op). Trash orchestration is now handled via `FileOperations`.
!Caveat: Conflict resolution via `resolver` callback is synchronous (uses Qt nested event loop).

### [FILE: undo_manager.py] [USABLE]
Role: Stack-based tracker for reversing completed file operations.

/DNA/: [tm:historyCommitted(tx) -> _undo_stack.append(tx)] -> [undo() -> tx.ops.reverse() -> _perform_inversion() -> call:file_ops method -> wait for job_id completion]

- SrcDeps: core.transaction, core.backends.gio.helpers
- SysDeps: PySide6.QtCore, collections.deque, enum

API:
  - undo() / redo(): pops transaction, generates reciprocal ops.
  - setFileOperations(file_ops): injects the I/O executor.
  - can_undo() / can_redo() => bool: stack and status check.
  Signals: stackChanged, undoTriggered, redoTriggered, busyChanged, operationFinished.
!Caveat: Operations that failed or are pending in the original transaction are skipped during inversion.
!Caveat: The Undo/Redo stack is limited to 50 historical transactions.
