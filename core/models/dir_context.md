Identity: core/models — Pure data-transfer objects. Zero GIO, zero Qt Widget dependencies (FileJob imports QObject for signals only).

!Rule: [No business logic in models] - Reason: Models are structs; logic belongs in managers or backends.
!Pattern: [slots=True on FileJob] - Reason: Reduces per-instance overhead; FileJob is created per operation, high frequency.

---

### [FILE: __init__.py] [DONE]
Role: Re-exports FileInfo, FileJob, FileOperationSignals, TrashItem for single-import convenience.

/DNA/: Flat re-export only.

---

### [FILE: file_info.py] [DONE]
Role: Unified file metadata struct. Shared across scanner, metadata provider, and UI layers.

/DNA/: Immutable dataclass (kw_only=True); fields cover path, URI, display name, size, timestamps, permissions, trash metadata.

- SysDeps: dataclasses

API:
  - FileInfo(dataclass, kw_only=True):
    fields: path, uri, name, display_name, size, size_human, is_dir, is_symlink,
            symlink_target, is_hidden, mime_type, icon_name, modified_ts, accessed_ts,
            created_ts, mode, permissions_str, owner, group, can_write,
            target_uri, trash_orig_path, trash_deletion_date

---

### [FILE: file_job.py] [DONE]
Role: Tracks a single file operation; also hosts FileOperationSignals hub.

/DNA/: `FileJob(slots=True)` carries op metadata -> submitted to backend -> backend assigns `cancellable`; `FileOperationSignals(QObject)` owns all signals emitted by runnables.

- SysDeps: dataclasses, PySide6{QtCore}

API:
  - FileJob(dataclass, slots=True):
    fields: id, op_type, source, dest, transaction_id, cancellable, auto_rename,
            skipped_files, overwrite, rename_to, status,
            items (batch), ui_refresh_rate_ms, halt_on_error

  - FileOperationSignals(QObject):
    signals: started(job_id, op_type, source), progress(job_id, current, total),
             finished(tid, job_id, op_type, result_path, success, message),
             operationError(tid, job_id, op_type, path, message, conflict_data),
             itemListed(TrashItem), trashNotSupported(path, error),
             batchAssessmentReady(tid, valid_items, conflicts),
             batchProgress(tid, completed, total, filename),
             batchFinished(tid, successful_items, failed_items)

!Caveat: `cancellable` field type is `object` (not typed as `Gio.Cancellable`) to avoid GIO import in the model layer; cast at backend.

---

### [FILE: trash_item.py] [DONE]
Role: Lightweight struct representing a trash entry; emitted via itemListed signal.

/DNA/: Plain dataclass; no logic, no Qt.

- SysDeps: dataclasses

API:
  - TrashItem(dataclass):
    fields: trash_name, display_name, original_path, deletion_date, trash_uri, size, is_dir
