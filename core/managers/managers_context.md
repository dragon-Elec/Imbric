Identity: /Imbric/core/managers - High-level operation controllers. Orchestrate the job lifecycle between UI bridges and VFS backends.

!Rule: [Always assert registry before use] - Reason: Registry is injected post-construction via `setRegistry`; unguarded calls on unset registry will raise AttributeError at runtime.
!Pattern: [Job Linkage] - Reason: `_create_job` calls `TransactionManager.addOperation` before submit to ensure end-to-end cancellation tracking.

Index:
- None: This directory only contains the primary FileOperations controller.

### [FILE: file_operations.py] [USABLE]
Role: Unified controller for all file I/O (Copy, Move, Trash, Restore, Batch). Routes jobs to backends via BackendRegistry.

/DNA/: [copy/move/rename(...) -> _create_job(op_type, src, dest, tid) -> if(tid): call:tm.addOperation() -> _submit(job, backend.method) -> wait operationFinished]
/DNA/: [assessBatch(tid, sources, dest, mode) -> call:QThreadPool.start(BatchAssessmentRunnable) -> wait assessmentReady -> em:batchAssessmentReady]

- SrcDeps: core.models{FileJob, FileOperationSignals, TrashItem}, core.registry, core.backends.gio.metadata_workers{UniqueNameWorker, ExistenceWorker}, core.utils.path_ops
- SysDeps: PySide6{QtCore}, os, uuid

API:
  - FileOperations(QObject):
    Signals: operationStarted, operationProgress, operationFinished, operationError, itemListed, trashNotSupported, batchAssessmentReady, batchProgress, batchFinished, uniqueNameReady, existenceReady.
    - setRegistry(registry: BackendRegistry) -> None: wires internal signals to public signals.
    - setTransactionManager(tm) / setUndoManager(um) -> None
    - copy/move/rename/transfer(src, dest, tid, overwrite, auto_rename) -> str: returns job_id.
    - transfer_batch(tid, items, refresh_ms, halt_on_error) -> str: True batching dispatcher.
    - assessBatch(tid, sources, dest_dir, mode, resolver) -> None: runs pre-flight in background.
    - trash(path, tid) / restore(original_path, tid, overwrite, rename_to) -> str
    - restore_from_trash(path) -> str: alias for restore.
    - execute_inverse_payload(payload: dict) -> str: executes reciprocal action for undo.
    - trashMultiple(paths: list) -> None: Internal transaction aggregation.
    - listTrash() / emptyTrash() -> str: Remote VFS trash management.
    - createFolder/createFile(path, tid, auto_rename) -> str
    - createSymlink(target, path, tid, auto_rename) -> str
    - check_exists(path) / is_same_file(path_a, path_b) -> bool
    - generate_unique_name(dest, style) -> str: Synchronous version for internal use.
    - check_exists_async/get_unique_name_async(task_id, path, style) -> None: Background workers.
    - cancel(job_id) / cancelAll() -> None: aborts active jobs.
    - activeJobCount() / jobStatus(job_id) -> int / str: tracking utilities.
    - shutdown() -> None: cancels all and waits for thread pool.
  - BatchAssessmentRunnable(QRunnable):
    - run(): Background task to compute valid/conflicting items before operation start.
!Caveat: `restore_from_trash` is an alias for `restore` for legacy compatibility.
!Caveat: `setRegistry` must be called before ANY operation method; all operations assert `self._registry`.
