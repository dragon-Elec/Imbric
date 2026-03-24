Identity: core/managers — High-level operation controllers. Sit between UI and backends; own the job lifecycle.

!Rule: [Always assert registry before use] - Reason: Registry is injected post-construction; unguarded calls on unset registry raise AttributeError at runtime.
!Pattern: [job_id links UI Transaction to backend job] - Reason: `_create_job` calls `TransactionManager.addOperation` before dispatching so cancellation is tracked end-to-end.

---

### [FILE: file_operations.py] [DONE]
Role: Unified controller for all file I/O (copy, move, rename, trash, restore, batch, create). Routes jobs to backends via BackendRegistry.

/DNA/: `copy/move/rename/...` -> `_create_job(op_type, src, dest, tid)` [if tid: tm.addOperation] -> `_submit(job, backend.method)` -> `_jobs[job.id]=job` -> backend.method(job) [runs QRunnable] -> signals.finished -> `_on_finished` -> delete _jobs[job_id] -> em:operationFinished

Batch path: `transfer_batch(tid, items)` -> `FileJob(op_type="batch_transfer", items=[...])` -> backend.batch_transfer(job) -> signals.batchFinished -> `_on_batch_finished` -> loop: _on_finished per item -> em:batchFinished

Pre-flight: `assessBatch(tid, sources, dest_dir, mode)` -> `BatchAssessmentRunnable.run()` [background] -> checks exists + same_file + dest_collision -> em:batchAssessmentReady(tid, valid, conflicts)

- SrcDeps: core.models{FileJob, FileOperationSignals, TrashItem}, core.registry, core.utils.path_ops
- SysDeps: PySide6{QtCore}, os, uuid

API:
  - FileOperations(QObject):
    Signals: operationStarted, operationProgress, operationFinished, operationError,
             itemListed(TrashItem), trashNotSupported,
             batchAssessmentReady(tid, valid, conflicts),
             batchProgress, batchFinished

    - setRegistry(registry: BackendRegistry) -> None: injects registry + wires signals via _setup_signals
    - setTransactionManager(tm) -> None
    - setUndoManager(undo_manager) -> None

    - copy(source, dest, tid, overwrite, auto_rename) -> str
    - move(source, dest, tid, overwrite) -> str
    - transfer(source, dest, mode, tid, overwrite, auto_rename) -> str
    - transfer_batch(tid, items, ui_refresh_rate_ms, halt_on_error) -> str
    - assessBatch(tid, sources, dest_dir, mode) -> None
    - rename(path, new_name, tid) -> str
    - createFolder(path, tid, auto_rename) -> str
    - createFile(path, tid, auto_rename) -> str
    - createSymlink(target, link_path, tid, auto_rename) -> str

    - trash(path, tid) -> str
    - trashMultiple(paths: list) -> None: creates batch transaction internally
    - restore(original_path, tid, overwrite, rename_to) -> str
    - listTrash() -> str
    - emptyTrash() -> str

    - check_exists(path) -> bool
    - is_same_file(path_a, path_b) -> bool
    - generate_unique_name(dest_path, style='copy') -> str
    - cancel(job_id=None) -> None
    - activeJobCount() -> int
    - shutdown() -> None

  - BatchAssessmentRunnable(QRunnable):
    - run(): per-source: check_exists -> build_dest_path -> is_same_file -> check_exists(dest) -> emit batchAssessmentReady

!Caveat: `delete()` is absent; permanent delete falls through to `trash()` in `GIOBackend` — no hard-delete runnable exists yet.
!Caveat: `restore_from_trash(original_path)` is an alias for `restore()` kept for legacy compat; prefer `restore()`.
!Caveat: `setRegistry` must be called before ANY operation method; all operation methods assert self._registry.
