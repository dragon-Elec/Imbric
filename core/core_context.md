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
- services/: Stateless logic (Validator, Search).
- threading/: AsyncWorkerPool (QTOAST) bridge.
- utils/: Shared path and formatting helpers.

### [FILE: registry.py] [USABLE]
Role: BackendRegistry — URI-scheme-to-backend dispatcher for agnostic I/O. Supports strict VFS enforcement mode.

/DNA/: [register_io(scheme, backend) -> _io_backends[scheme]=backend] -> [get_io(path) -> if("://" in path) => _io_backends[scheme] | else: _default_io] + [set_strict_vfs(True) -> unknown schemes raise RuntimeError instead of silent fallback]

- SrcDeps: core.interfaces{IOBackend, ScannerBackend, ThumbnailProviderBackend, MetadataProvider, MonitorBackend, DeviceProvider, MetadataWorkers, SearchBackend}, core.models.file_job
- SysDeps: (none)

API:
  - BackendRegistry:
    - register_io(scheme, backend) / set_default_io(backend) / get_io(path_or_uri) => IOBackend | None
    - get_io_id(path_or_uri) -> str: returns the scheme key or "default".
    - get_registered_schemes() -> list[str]: introspection helper.
    - set_strict_vfs(enabled: bool) / is_strict_vfs() -> bool: when enabled, unknown schemes raise RuntimeError.
    - register_scanner(scheme, backend) / set_default_scanner(backend) / get_scanner(path_or_uri) => ScannerBackend | None
    - register_thumbnail(backend) / get_thumbnail(mime_type) => ThumbnailProviderBackend | None
    - set_metadata_provider(provider) / get_metadata() => MetadataProvider | None
    - set_monitor_backend(backend) / get_monitor() => MonitorBackend | None
    - set_device_provider(provider) / get_devices() => DeviceProvider | None
    - set_worker_classes(count_cls, dim_cls) / create_count_worker() / create_dimension_worker()
    - get_io_signals() => FileOperationSignals
    - set_search_backend(backend) / get_search() => SearchBackend | None
!Caveat: `get_io_signals` returns the shared `FileOperationSignals` hub used by all registered backends.
!Caveat: `get_io` and `get_scanner` raise RuntimeError in strict mode when no backend matches the scheme.

### [FILE: transaction.py] [USABLE]
Role: Data models for batch operation tracking and state serialization.

/DNA/: [Transaction(dataclass) -> add_operation(op) -> ops.append(op) ++ total_ops] -> [find_operation(job_id) => TransactionOperation]

- SrcDeps: core.models.file_job{InversePayload}
- SysDeps: dataclasses, enum, time, typing

API:
  - TransactionStatus(Enum): PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, PARTIAL.
  - TransactionOperation(dataclass): op_type, src, dest, result_path, job_id, backend_id, inverse_payload, status, error.
  - Transaction(dataclass): id, description, created_at, ops, total_ops, completed_ops, status, error_message, is_committed, is_reversible.
    - add_operation(op: TransactionOperation): registers atomic unit.
    - get_progress() => float: returns progress 0.0 to 1.0.
    - find_operation(job_id: str) => TransactionOperation | None.
    - update_status(job_id: str, status: TransactionStatus, error: str = "").

### [FILE: transaction_manager.py] [USABLE]
Role: Central CNS; orchestrates batch lifecycle and tracks high-level progress.

/DNA/: [batchTransfer(sources, dest) -> startTransaction(tid) -> call:file_ops.assessBatch() -> wait assessmentReady -> call:file_ops.transfer_batch() -> onOperationFinished() -> em:transactionProgress] + [onOperationError() -> if(conflict) -> _pending_conflicts[job_id]=data -> em:conflictDetected -> wait -> resolveConflict() -> execute resolution]

- SrcDeps: core.transaction, core.utils.path_ops
- SysDeps: PySide6{QtCore}, uuid, typing

API:
  - startTransaction(description, is_reversible=True) => tid
  - addOperation(tid, op_type, src, dest="", job_id="") -> None
  - batchTransfer(sources, dest_dir, mode="auto", conflict_resolver=None) -> None: high-level entry point.
  - resolveConflict(job_id, resolution, new_name="") -> None: executes resolution via file_ops.
  - commitTransaction(tid) -> None: marks population done, closes if all ops finished.
  - setFileOperations(file_ops) / setValidator(validator) / setTrashManager(tm): dependency injection.
  - onBatchAssessmentReady(tid, valid, conflicts) / onOperationStarted(job_id, type, path) / onOperationProgress(job_id, current, total) / onOperationFinished(tid, job_id, op_type, result_path, success, message, inverse_payload=None) / onOperationError(tid, job_id, op_type, path, message, conflict_data): signal handlers.
  Signals: transactionStarted(tid, desc), transactionFinished(tid, status), transactionProgress(tid, pct), historyCommitted(tx), conflictDetected(jid, data), conflictResolved(jid, res), transactionUpdate(tid, desc, compl, total), jobCompleted(op, res, msg), operationFailed(op, path, msg).
!Caveat: `setTrashManager` is a legacy stub (no-op). Trash orchestration is now handled via `FileOperations`.
!Caveat: Conflict resolution via `resolver` callback in `onBatchAssessmentReady` is synchronous (uses Qt nested event loop).

### [FILE: undo_manager.py] [USABLE]
Role: Stack-based tracker for reversing completed file operations.

/DNA/: [tm:historyCommitted(tx) -> _undo_stack.append(tx)] -> [undo() -> tx.ops.reverse() -> _perform_inversion() -> call:file_ops.execute_inverse_payload() | method -> wait for job_id(s) completion -> _finalize_pending()]

- SrcDeps: core.transaction{Transaction, TransactionStatus}, core.utils.vfs_path{vfs_basename}
- SysDeps: PySide6.QtCore, collections.deque, enum

API:
  - undo() / redo(): pops transaction, generates reciprocal ops, enters busy state.
  - setFileOperations(file_ops): injects the I/O executor and connects async handlers.
  - can_undo() / can_redo() => bool: stack and status check.
  Signals: stackChanged(can_undo, can_redo), undoTriggered(desc), redoTriggered(desc), busyChanged(busy), operationFinished(success, msg).
!Caveat: Operations that are not in COMPLETED status (FAILED/CANCELLED) are skipped during inversion.
!Caveat: The Undo/Redo stack is limited to 50 historical transactions.
!Caveat: Uses `inverse_payload` if available for complex reversals (e.g. multi-step Move/Restore).

### [FILE: utils/vfs_enforce.py] [USABLE]
Role: VFS enforcement helpers that force UI layer to route through BackendRegistry.

/DNA/: [normalize_to_uri(path) -> if no scheme prepend file://] + [require_vfs_path(path, registry) -> assert backend exists else RuntimeError] + [is_vfs_routable(path, registry) -> bool check]

- SrcDeps: None
- SysDeps: (none)

API:
  - normalize_to_uri(path: str) -> str: converts plain POSIX paths to file:// URIs.
  - require_vfs_path(path: str, registry, operation: str) -> None: raises RuntimeError if no backend registered.
  - is_vfs_routable(path: str, registry) -> bool: safe check without raising.
