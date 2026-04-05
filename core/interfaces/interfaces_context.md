1. Identity: /Imbric/core/interfaces — ABC layer defining every backend contract. Any new backend must implement these protocols.

!Decision: [ABCs > duck-typing] - Reason: Enforces contract completion at instantiation time; prevents silent partial implementations.
!Pattern: [IO via FileJob] - Reason: All IOBackend methods accept a FileJob and return job_id (str); result is surfaced via signals, never return value.

---

### [FILE: __init__.py] [USABLE]
Role: Re-exports core ABCs for single-import convenience.

/DNA/: `from core.interfaces import IOBackend, ...` -> core 7 ABCs available.

- SysDeps: (none — pure re-export)

---

### [FILE: io_backend.py] [USABLE]
Role: ABC for all file I/O (copy, move, trash, restore, delete, create, rename, symlink).

/DNA/: All methods accept `FileJob` -> return `job_id: str`; contract mandates callers receive outcome via `FileOperationSignals`, not return value.

- SysDeps: abc, enum, typing, core.models.file_job{FileJob, InversePayload}

API:
  - BackendFeature(StrEnum): SYMLINK, TRASH, HARDLINK, PERMISSIONS, SEARCH.
  - IOBackend(ABC):
    - supports_feature(feature: BackendFeature) -> bool: queries backend capabilities.
    - set_signals(signals) -> None: injects global signal hub.
    - build_inverse_payload(job, result_path) -> InversePayload | None: for UndoManager.
    - copy(job) / move(job) / batch_transfer(job) -> str: transfer operations.
    - trash(job) / restore(job) / delete(job) -> str: deletion and trash lifecycle.
    - create_folder(job) / create_file(job) / rename(job) / create_symlink(job) -> str: creation and naming.
    - list_trash(job) / empty_trash(job) -> str: trash management.
    - query_exists(path) -> bool
    - is_same_file(path_a, path_b) -> bool
    - is_directory(path) / is_symlink(path) / is_regular_file(path) -> bool.
    - get_local_path(path) -> str | None.

---

### [FILE: scanner_backend.py] [USABLE]
Role: ABC for directory scanning; results delivered via signals, not returns.

/DNA/: `scan_directory(path)` -> emits file-discovery signals; `cancel()` -> halts scan in progress.

- SysDeps: abc

API:
  - ScannerBackend(ABC):
    - scan_directory(path) -> None
    - scan_single_file(path) -> None
    - cancel() -> None

---

### [FILE: metadata_provider.py] [USABLE]
Role: ABC for synchronous (blocking) metadata retrieval.

/DNA/: `get_file_info(path_or_uri)` => `FileInfo | None`; `get_dimensions` and `get_item_count` may return sentinel (`None`/`-1`) for async-only impls.

- SysDeps: abc, typing, core.models.file_info{FileInfo}

API:
  - MetadataProvider(ABC):
    - get_file_info(path_or_uri, attributes=None) -> FileInfo | None
    - get_dimensions(path_or_uri) -> tuple[int, int] | None
    - get_item_count(path) -> int: -1 on error

---

### [FILE: thumbnail_provider.py] [USABLE]
Role: ABC for thumbnail generation; providers stacked in registry, first-match wins.

/DNA/: `supports(mime_type)` => bool; `if True` -> `generate(uri, mime, mtime)` => thumb_path | None; `lookup` checks cache before generate.

- SysDeps: abc

API:
  - ThumbnailProviderBackend(ABC):
    - supports(mime_type) -> bool
    - generate(uri, mime_type, mtime) -> str | None
    - lookup(uri, mtime) -> str | None

---

### [FILE: cache_provider.py] [USABLE]
Role: ABC for mount-scoped cache layer (get/set/invalidate/warm/clear).

/DNA/: `get(key)` => cached value or None; `warm(path)` pre-fills cache aggressively; `clear()` nukes all entries.

- SysDeps: abc, typing

API:
  - CacheProvider(ABC):
    - get(key) -> object | None
    - set(key, value) -> None
    - invalidate(key) -> None
    - warm(path) -> None
    - clear() -> None

---

### [FILE: search_backend.py] [USABLE]
Role: ABC for live file search (filename/content/fuzzy). Results stream via signals.

/DNA/: `[search(query, path, mode, options) -> resultsReady(list) -> searchFinished(sid)]` + `[cancel() -> halts stream]`

- SysDeps: abc, PySide6{QtCore}

API:
  - SearchBackend(ABC, QObject):
    - search(query, path, mode, options) -> None: asynchronous streaming search.
    - cancel() -> None: terminates current search session.
    - Signals: resultsReady(list), searchFinished(sid), searchError(msg)

---

### [FILE: monitor_backend.py] [USABLE]
Role: QObject-based ABC for directory change monitoring (Inotify/GFileMonitor).

/DNA/: `[watch(path) -> watchReady | watchFailed] -> [fileCreated | fileDeleted | fileChanged | fileRenamed | directoryChanged]`

- SysDeps: PySide6{QtCore}

API:
  - MonitorBackend(QObject):
    - watch(directory_path) -> None: starts watching.
    - stop() -> None: terminates current watcher.
    - currentPath() -> str: returns the watched directory path.
    - Signals: fileCreated(path), fileDeleted(path), fileChanged(path), fileRenamed(old, new), directoryChanged, watchReady(path), watchFailed(reason)

---

### [FILE: device_provider.py] [USABLE]
Role: QObject-based ABC for volume and MTP device monitoring and lifecycle.

/DNA/: `[mount_volume(id) -> mountSuccess | mountError]` + `[unmount_volume(id) -> volumesChanged]`

- SysDeps: PySide6{QtCore}

API:
  - DeviceProvider(QObject):
    - get_volumes() -> list: dictionary items for each volume/mount.
    - mount_volume(identifier) / unmount_volume(identifier) -> None: lifecycle control.
    - title / icon Properties: UI integration metadata.
    - Signals: volumesChanged, mountSuccess(id), mountError(msg)

---

### [FILE: metadata_workers.py] [USABLE]
Role: Contracts for high-frequency, async metadata extraction (counts, dimensions).

/DNA/: `[enqueue(uri, path) -> worker processing -> dimensionsReady | countReady]` + `[clear() -> empty queue]`

- SysDeps: PySide6{QtCore}

API:
  - ItemCountWorkerBackend(QObject):
    - enqueue(uri, path) / clear() -> None
    - Signals: countReady(path, count)
  - DimensionWorkerBackend(QObject):
    - enqueue(uri, path) / clear() -> None
    - Signals: dimensionsReady(id, w, h)

---

### [FILE: cancellation.py] [USABLE]
Role: Abstract base for backend-neutral cancellation tokens.

/DNA/: [call:cancel() -> is_cancelled() => true]

- SysDeps: abc{ABC, abstractmethod}

API:
  - CancellationToken(ABC):
    - cancel() -> None: triggers the cancellation state.
    - is_cancelled() -> bool: checks for active cancellation request.
