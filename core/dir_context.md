# Imbric Core: I/O & Transaction Logic
Role: Central business logic, VFS abstraction (Gio), and thread-safe file operations.

## Maintenance Rules
- Non-Blocking: Never perform Gio I/O in main thread. Use QThreadPool.
- Gio Priority: Use Gio for all operations (supports network/MTP). Avoid os except for local speed (scandir).
- Atomic Renames: All creation ops must use the atomic retry-loop pattern to prevent collisions.
- Error Handling: Use PARTIAL:N signal strings for batch failures; don't halt on first error.

## Atomic Notes (Architectural Truths)
- !Decision: [Gio >> os.stat/shutil] - Reason: VFS transparency. Python `os` fails on MTP (phones) and GDrive mounts. Gio is mandatory for Linux Desktop parity.
- !Rule: [Signalling > Direct Call] - Reason: Thread-safety. Background workers MUST emit signals; never mutate UI objects directly.
- !Rule: [QTOAST vs TM] - Reason: QTOAST handles generic Read-Only/Background tasks. `TransactionManager` owns Destructive/Interactive VFS tasks required for Cancel/Undo tracking and conflict resolution.
- !Pattern: [UUID-Linkage] - Reason: Job traceability. Every backend job must carry a UUID that matches its UI-layer Transaction entry.

## Sub-Directory Index
- gio_bridge/: Async scanners, directory monitors, and mount bridges.
- image_providers/: QML-registered providers for thumbnails (GnomeDesktop) and theme icons.
- utils/: Common utilities including GioWorkerPool (QTOAST) for async tasks.

## Module Audits

### [FILE: [transaction.py](./transaction.py)] [DONE]
Role: Data models for batch operations and status tracking.

/DNA/: [TransactionStatus(Enum) -> TransactionOperation(dataclass) -> Transaction(dataclass) -> add_operation() -> find_operation(job_id) => TransactionOperation]

- SrcDeps: None
- SysDeps: dataclasses, typing, enum, time

API:
  - TransactionStatus(Enum): PENDING, RUNNING, COMPLETED, FAILED, CANCELLED.
  - TransactionOperation(dataclass): op_type, src, dest, job_id, status, error.
  - Transaction(dataclass): id, description, ops, total_ops, completed_ops, status.
    - [add_operation()](./transaction.py#L44)(op): Registers new atomic unit.
    - [get_progress()](./transaction.py#L48)() => float: 0.0 to 1.0.

### [FILE: [file_operations.py](./file_operations.py)] [DONE]
Role: Orchestrates low-level Gio I/O via QThreadPool workers.

/DNA/: [Slot -> _create_job(uuid4) -> tid.addOperation() -> _submit(QThreadPool) -> em:operationStarted -> [Worker.run() -> em:finished] -> del _jobs[id]]

- SrcDeps: .file_workers, .trash_workers
- SysDeps: PySide6.QtCore (QObject, Signal, Slot, QThreadPool, QMutex), uuid.uuid4

API:
  - [copy/move/transfer/rename](./file_operations.py#L103-L131)(paths, tid): Job Factory + Submission.
  - [trash/trashMultiple](./file_operations.py#L156-L175)(paths, tid): VFS trash orchestration.
  - [restore](./file_operations.py#L179)(orig_path, tid): Specific reversal from trash://.
  - [generate_unique_name](./file_operations.py#L225)(dest, style) => str: Collision-safe path generator.
!Caveat: `_create_job` registers with `TransactionManager` BEFORE returning, ensuring job-ID linkage exists before the worker starts.

### [FILE: [transaction_manager.py](./transaction_manager.py)] [DONE]
Role: Central hub bridging UI bridges to FileOperations; owns conflict state.

/DNA/: [batchTransfer() -> startTransaction() -> file_ops.transfer() -> onOperationFinished() -> if(all_done) -> em:historyCommitted]
/DNA/: [onOperationError() -> if(conflict) -> _pending_conflicts.add(job_id) -> em:conflictDetected -> wait -> resolveConflict() -> file_ops.retry()]

- SrcDeps: .transaction, .file_operations, .operation_validator
- SysDeps: PySide6.QtCore (QObject, Signal, Slot), uuid.uuid4

API:
  - [startTransaction](./transaction_manager.py#L63)(desc) => tid: Initialize batch tracking.
  - [batchTransfer](./transaction_manager.py#L152)(sources, dest_dir, mode, resolver): Core I/O loop with conflict gating.
  - [resolveConflict](./transaction_manager.py#L92)(job_id, resolution, new_name): Resumes operations from UI-provided choice.
!Contract: Transaction ONLY closes (commits to history) when `completed_ops == total_ops`.

### [FILE: [undo_manager.py](./undo_manager.py)] [DONE]
Role: Life-cycle tracker for reversible file operations (Stack).

/DNA/: [tm:historyCommitted(tx) -> deque.append(tx) -> em:canUndoChanged] -> [undo() -> tx.reverse() -> file_ops.exec()]

- SrcDeps: .transaction_manager, .file_operations, .transaction
- SysDeps: PySide6.QtCore (QObject, Signal), collections.deque

API:
  - canUndo / canRedo (Property): UI state binding.
  - [undo()/redo()](./undo_manager.py#L68): Pops transaction, generates reciprocal operations.
!Caveat: Physical deletion (Empty Trash) is irreversible. Sourced from `trash_workers`.

### [FILE: [metadata_utils.py](./metadata_utils.py)] [DONE]
Role: Static utility for deep Gio attribute extraction and icon resolution.

/DNA/: [path -> Gio.File -> query_info(ATTRS_FULL) -> FileInfo(dataclass) -> resolve_mime_icon()]

- SrcDeps: None
- SysDeps: gi.repository.Gio, dataclasses, stat, datetime

API:
  - [get_file_info](./metadata_utils.py#L179)(path) => FileInfo: Hydrated metadata or None.
  - [resolve_mime_icon](./metadata_utils.py#L143)(gfile) => str: Direct GIcon-to-ThemeName mapping.
  - [format_size](./metadata_utils.py#L102)(bytes) => str: Human-friendly units.

### [FILE: [file_workers.py](./file_workers.py)] [DONE]
Role: Multithreaded implementations of VFS operations.

/DNA/: [QRunnable.run() -> Gio.File.copy/move() -> wait -> if(X-Device) -> recursive_copy() -> em:finished]

- SrcDeps: .metadata_utils
- SysDeps: PySide6.QtCore (QRunnable), gi.repository (Gio, GLib)

API:
  - TransferRunnable: Copy/Move/Transfer with per-file progress signaling.
  - CreateFolder/CreateFile/CreateSymlinkRunnable: Specialized atomic creation.
  - RenameRunnable: Specific wrap for `standard::display-name`.
!Caveat: Moves across mount points fallback to copy+delete automatically.

### [FILE: [file_monitor.py](./file_monitor.py)] [DONE]
Role: Wraps Gio.FileMonitor for directory change tracking.

/DNA/: [watch(path) -> gfile.monitor_directory(WATCH_MOVES) -> on_changed -> if(EVENT) -> em:fileSignal -> debounce -> em:directoryChanged]

- SrcDeps: None
- SysDeps: gi.repository (Gio, GLib), PySide6.QtCore (QObject, Signal, Slot, QTimer)

API:
  - [watch](./file_monitor.py#L51)(directory_path): Starts monitoring with WATCH_MOVES.
  - [stop](./file_monitor.py#L86)(): Cancels monitor and disconnects signals.
!Decision: [Debounce (200ms)] - Reason: Coalesces rapid events (like directory bulk creation) to prevent UI freezing.

### [FILE: [operation_validator.py](./operation_validator.py)] [DONE]
Role: Post-operation verification layer using QThreadPool.

/DNA/: [validate(job) -> ValidationRunnable -> checker(src, dest) -> query_exists() => em:validationPassed]

- SrcDeps: .file_workers
- SysDeps: gi.repository.Gio, PySide6.QtCore (QObject, Signal, QRunnable, QThreadPool)

API:
  - [validate](./operation_validator.py#L46)(job_id, op_type, source, result_path, success): Queues verification runnable.
!Rule: [Fire-and-Forget] - Reason: Validation runs after transaction commit; failures do not roll back but notify UI of inconsistency.

### [FILE: [search.py](./search.py)] [WIP]
Role: Pluggable search engine interface (fd/fdfind vs os.scandir).

/DNA/: [get_search_engine() -> FdSearchEngine if available else ScandirSearchEngine]

- SrcDeps: None
- SysDeps: subprocess, fnmatch, os, shutil

API:
  - SearchEngine(ABC): Defines search() iterator and stop().
  - [get_search_engine](./search.py#L216)(): Factory for best performance (Rust-based `fd` preferred).
  - [FileSearch](./search.py#L236)(QObject): Legacy Qt-compatible wrapper.

### [FILE: [search_worker.py](./search_worker.py)] [WIP]
Role: QThread wrapper for SearchEngine results streaming.

/DNA/: [start_search() -> QThread.run() -> for path in engine.search() -> batch.append(50) -> em:resultsFound]

- SrcDeps: .search
- SysDeps: PySide6.QtCore (QThread, Signal, Slot, QMutex)

API:
  - [start_search](./search_worker.py#L52)(directory, pattern, recursive): Runs search in background.
!Rule: [Path-Only Streaming] - Reason: Search yields raw paths; metadata is fetched lazily by UI only for visible items.

### [FILE: [sorter.py](./sorter.py)] [DONE]
Role: High-performance list sorting with natural string support.

/DNA/: [sort(files) -> if(foldersFirst) -> split -> sort(natural) -> combine]

- SrcDeps: None
- SysDeps: re, enum, PySide6.QtCore (QObject, Signal, Slot, Property)

API:
  - [sort](./sorter.py#L62)(files, key, ascending): Returns new sorted list.
!Pattern: [Natural Sort] - Reason: Standard Python sort puts "file10" before "file2". Regex split handles numeric sequences.

### [FILE: [trash_workers.py](./trash_workers.py)] [DONE]
Role: Gio-specific trash operations (List, Restore, Empty).

/DNA/: [Restore -> enumerate(trash:///) -> match(orig-path) -> latest_date -> move(dest)]

- SrcDeps: .file_workers, .metadata_utils
- SysDeps: gi.repository (Gio, GLib)

API:
  - SendToTrashRunnable: Specialized mover to trash:/// URI.
  - RestoreFromTrashRunnable: Specialized mover from trash:/// to original path.
  - ListTrashRunnable: yields TrashItem objects with original paths.
  - EmptyTrashRunnable: recursive physical deletion from trash root.
!Caveat: Restore matches based on the LATEST deletion date if multiple entries for the same path exist.
