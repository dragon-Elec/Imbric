1. Identity: /Imbric/core/models — Pure data-transfer objects. Zero GIO, zero Qt Widget dependencies (FileJob imports QObject for signals only).

!Rule: [No business logic in models] - Reason: Models are structs; logic belongs in managers or backends.
!Pattern: [slots=True on FileJob] - Reason: Reduces per-instance overhead; FileJob is created per operation, high frequency.

---

### [FILE: __init__.py] [USABLE]
Role: Re-exports FileInfo, FileJob, FileOperationSignals, TrashItem, and Transaction-related objects for single-import convenience.

/DNA/: `from core.models import ...` -> re-exports local models + core.transaction objects.

- SrcDeps: core.transaction{Transaction, TransactionOperation, TransactionStatus}

---

### [FILE: file_info.py] [USABLE]
Role: Unified file metadata struct. Shared across scanner, metadata provider, and UI layers.

/DNA/: Immutable dataclass (kw_only=True); fields cover path, URI, display name, size, timestamps, permissions, trash metadata.

- SysDeps: dataclasses

API:
  - FileInfo(dataclass, kw_only=True):
    - fields: path, uri, name, display_name, size, size_human, is_dir, is_symlink,
             symlink_target, is_hidden, mime_type, icon_name, modified_ts, accessed_ts,
             created_ts, mode, permissions_str, owner, group, can_write,
             target_uri, trash_orig_path, trash_deletion_date

---

### [FILE: file_job.py] [USABLE]
Role: Tracks a single file operation; also hosts FileOperationSignals hub.

/DNA/: `FileJob(slots=True)` carries op metadata -> submitted to backend -> backend assigns `cancellable` (token) and builds `inverse_payload` (undo) upon success.

- SysDeps: dataclasses, typing, PySide6{QtCore}, core.interfaces.cancellation{CancellationToken}

API:
  - InversePayload(TypedDict): action (trash/restore/rename/move), target, dest, new_name, rename_to, tid, backend_id.
  - FileJob(dataclass, slots=True):
    - fields: id, op_type (copy, move, trash, restore, rename, createFolder, list, empty, transfer),
             source, dest, transaction_id, cancellable, inverse_payload, auto_rename,
             skipped_files, overwrite, rename_to, status, backend_id,
             items (batch), ui_refresh_rate_ms, halt_on_error.

  - FileOperationSignals(QObject):
    - signals: started(job_id, op_type, source), progress(job_id, current, total),
             finished(tid, job_id, op_type, result_path, success, message, inverse_payload),
             operationError(tid, job_id, op_type, path, message, conflict_data),
             itemListed(TrashItem), trashNotSupported(path, error),
             batchAssessmentReady(tid, valid_items, conflicts),
             batchProgress(tid, completed, total, filename),
             batchFinished(tid, successful_items, failed_items)

!Caveat: `cancellable` field is a `CancellationToken` ABC; this allows backend-neutral cancellation without importing backend-specific tokens (like `Gio.Cancellable`) in the model layer.

---

### [FILE: trash_item.py] [USABLE]
Role: Lightweight struct representing a trash entry; emitted via itemListed signal.

/DNA/: Plain dataclass; no logic, no Qt.

- SysDeps: dataclasses

API:
  - TrashItem(dataclass):
    - fields: trash_name, display_name, original_path, deletion_date, trash_uri, size, is_dir
