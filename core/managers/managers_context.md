Identity: /Imbric/core/managers - High-level controllers orchestrating job lifecycles between UI bridges and VFS backends.

Rules:
- [Assert Registry] MUST assert `self._registry` before use; it is injected post-constructor via `setRegistry`.
- [Signalling] MUST emit `operationStarted`/`operationFinished` for all I/O to maintain `TransactionManager` state.

Atomic Notes:
- !Pattern: [Job Linkage] - Reason: `_create_job` registers operations with `TransactionManager` BEFORE submission to ensure end-to-end cancellation tracking.
- !Pattern: [Deferred Signal Wiring] - Reason: Signals are linked during `setRegistry` when `FileOperationSignals` hub becomes available from the `BackendRegistry`.

Index:
- None: This package primarily houses the singular `FileOperations` orchestrator.

Audits:

### [FILE: file_operations.py] [USABLE]
Role: Unified controller for all file I/O operations (Copy, Move, Trash, etc). Routes jobs to backends via BackendRegistry.

/DNA/: [copy/move/rename(...) -> _create_job(op_type, src, dest, tid) -> if(tid): call:tm.addOperation() -> _submit(job, backend.method) -> wait operationFinished]
/DNA/: [assessBatch(tid, sources, dest, mode) -> call:QThreadPool.start(BatchAssessmentRunnable) -> wait assessmentReady -> em:batchAssessmentReady]

- SrcDeps: core.models{FileJob, FileOperationSignals, TrashItem}, core.registry.BackendRegistry, core.backends.gio.metadata_workers{UniqueNameWorker, ExistenceWorker}, core.utils{path_ops, vfs_path}
- SysDeps: PySide6.QtCore{QObject, Signal, Slot, QThreadPool, QMutex, QMutexLocker, Qt, QRunnable}, os, uuid

API:
  - FileOperations(QObject):
    Signals: operationStarted, operationProgress, operationFinished, operationError, itemListed, trashNotSupported, batchAssessmentReady, batchProgress, batchFinished, uniqueNameReady, existenceReady.
    - setRegistry(registry: BackendRegistry) -> None: wires internal signals to public signals.
    - setTransactionManager(tm) / setUndoManager(um) -> None
    - copy/move/rename/transfer(src, dest, tid, overwrite, auto_rename) -> str: returns job_id.
    - transfer_batch(tid, items, refresh_ms, halt_on_error) -> str: True batching dispatcher.
    - assessBatch(tid, sources, dest_dir, mode, resolver) -> None: runs pre-flight checks in background.
    - trash(path, tid) / restore(original_path, tid, overwrite, rename_to) -> str
    - restore_from_trash(path) -> str: alias for restore.
    - execute_inverse_payload(payload: dict) -> str: executes reciprocal action for undo/redo.
    - trashMultiple(paths: list) -> None: internal transaction aggregation.
    - listTrash() / emptyTrash() -> str: remote VFS trash management.
    - createFolder/createFile(path, tid, auto_rename) -> str
    - createSymlink(target, path, tid, auto_rename) -> str
    - check_exists(path) / is_same_file(path_a, path_b) -> bool: synchronous VFS helpers.
    - generate_unique_name(dest, style) -> str: synchronous conflict-free path generator.
    - check_exists_async/get_unique_name_async(task_id, path, style) -> None: background worker triggers.
    - cancel(job_id) / cancelAll() -> None: cancels specific or all active jobs.
    - activeJobCount() / jobStatus(job_id) -> int / str
    - shutdown() -> None: cancels all jobs and waits for thread pool.
  - BatchAssessmentRunnable(QRunnable):
    - run(): Background computation of valid items and conflicts before operation start.
!Caveat: `restore_from_trash` is a legacy alias for `restore`.
!Caveat: `setRegistry` MUST be called before ANY operation; all public I/O methods assert `self._registry`.
