Identity: core/backends/gio — GIO concrete implementations of IOBackend, ScannerBackend, MetadataProvider, FileMonitor, and VolumesBridge.

!Rule: [gi.require_version before every gi import] - Reason: Missing require_version silently uses wrong GLib version; causes hard-to-trace runtime errors.
!Decision: [Gio.Cancellable injected per-job] - Reason: Shared cancellables cause cross-job cancellation; each FileJob gets a fresh Gio.Cancellable in `GIOBackend._submit`.
!Pattern: [Runnable per operation] - Reason: All I/O runs in QThreadPool via QRunnable subclasses; GIOBackend._submit wraps any runnable class and injects cancellable.

Index:
- helpers.py — Path/URI utility functions (_make_gfile, ensure_uri, to_unix_timestamp).
- backend.py — GIOBackend (IOBackend) + GIOMetadataProvider (MetadataProvider).
- io_ops.py — QRunnable subclasses for copy/move/batch/rename/create/symlink.
- trash_ops.py — QRunnable subclasses for trash/restore/list_trash/empty_trash.
- scanner.py — FileScanner (ScannerBackend) for async directory enumeration.
- metadata.py — Synchronous `get_file_info()` function + async DimensionWorker/ItemCountWorker.
- metadata_workers.py — QRunnable workers for dimensions and item counts.
- monitor.py — FileMonitor (GIO directory watcher with debounce).
- volumes.py — VolumesBridge (VolumeMonitor wrapper with async usage cache).
- desktop.py — Desktop integration: recent files, bookmarks, app launchers.

---

### [FILE: helpers.py] [DONE]
Role: Shared GIO path/URI construction helpers. Imported across all gio sub-files.

/DNA/: `_make_gfile(path_or_uri)` => Gio.File.new_for_uri if "://" in str else new_for_path; `ensure_uri` -> commandline_arg parse => canonical URI.

- SysDeps: gi.repository{Gio}

API:
  - _make_gfile(path_or_uri: str) -> Gio.File
  - _gfile_path(gfile: Gio.File) -> str: get_path() or get_uri()
  - ensure_uri(path_or_uri: str) -> str
  - to_unix_timestamp(dt) -> int: GLib.DateTime -> int, 0 on None/error

---

### [FILE: backend.py] [DONE]
Role: GIOBackend implements IOBackend; GIOMetadataProvider implements MetadataProvider. Both delegate to low-level runnables/functions.

/DNA/: `GIOBackend._submit(job, RunClass)` -> if()!job.cancellable: assign Gio.Cancellable -> `RunClass(job, signals)` -> pool.start -> return job.id

- SrcDeps: .io_ops, .trash_ops, .scanner, .metadata, .helpers, core.interfaces{IOBackend, ScannerBackend, MetadataProvider}, core.models{FileJob, FileInfo}
- SysDeps: PySide6{QtCore}, gi.repository{Gio}

API:
  - GIOBackend(IOBackend):
    - copy, move, batch_transfer, trash, restore, list_trash, empty_trash: delegate to RunClass via _submit
    - delete(job) -> str: alias for trash (no hard-delete runnable)
    - create_folder, create_file, rename, create_symlink: delegate to RunClass
    - query_exists(path) -> bool: _make_gfile(path).query_exists(None)
    - is_same_file(path_a, path_b) -> bool: _make_gfile(a).equal(_make_gfile(b))

  - GIOMetadataProvider(MetadataProvider):
    - get_file_info(path_or_uri, attributes=None) -> FileInfo | None: calls metadata.get_file_info
    - get_dimensions(...) -> None: always None; dimensions handled async by DimensionWorker
    - get_item_count(...) -> -1: always -1; count handled async by ItemCountWorker

!Caveat: `delete()` falls through to `trash()`; no permanent-delete runnable. If hard delete is required, a DeleteRunnable must be added to io_ops.py.

---

### [FILE: monitor.py] [DONE]
Role: GIO directory watcher with 200ms debounce coalescing; emits Qt signals for UI refresh.

/DNA/: `watch(path)` -> [skip recent://, trash://] -> pool.enqueue(_setup_monitor_task) [background: Gio.File.monitor_directory] -> resultReady -> connect("changed", _on_changed); `_on_changed(event)` -> match event_type -> em:fileCreated|Deleted|Renamed|Changed + _debounce_timer.start -> timeout -> em:directoryChanged

- SrcDeps: core.threading.worker_pool
- SysDeps: PySide6{QtCore}, gi.repository{Gio, GLib}

API:
  - FileMonitor(QObject):
    Signals: fileCreated(path), fileDeleted(path), fileChanged(path), fileRenamed(old, new),
             directoryChanged(), watchReady(path), watchFailed(error)
    - watch(directory_path: str) -> None (slot)
    - stop() -> None (slot)
    - currentPath() -> str (slot)

!Caveat: `watch` silently returns (no-op) for `recent://` and `trash://` paths; monitor is never created.
!Caveat: Debounce timer (200ms) only fires `directoryChanged`; per-file signals (fileCreated, etc.) fire immediately without debounce.

---

### [FILE: volumes.py] [DONE]
Role: Wraps Gio.VolumeMonitor; provides cached volume list with lazy async disk-usage injection.

/DNA/: `__init__` -> connect monitor signals -> `_rebuild_cache_async` -> pool.enqueue("volumes_rebuild", _build_volume_list_task) [bg: iterate mounts/volumes] -> resultReady -> _cached_volumes = result -> em:volumesChanged; `get_volumes()` -> for each mounted: _get_usage(path) -> if cached: inject usage | else: pool.enqueue(_fetch_usage_task) -> on result: _usage_cache[path] = result -> em:volumesChanged

- SrcDeps: core.threading.worker_pool
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}

API:
  - VolumesBridge(QObject):
    Signals: volumesChanged(), mountSuccess(ident), mountError(message)
    Properties (constant): title="Devices", icon="hard_drive"
    - get_volumes() -> list[dict]: keys: identifier, name, path, icon, isMounted, canMount, canUnmount, type, usage?
    - mount_volume(identifier: str) -> None (slot)
    - unmount_volume(identifier: str) -> None (slot)

!Caveat: `_build_volume_list_task` is a static method that creates its own `Gio.VolumeMonitor.get()` inside the worker thread — safe because GVolumeMonitor uses GLib main context internally.
!Caveat: Usage is lazily fetched at `get_volumes()` call time; first call per path returns `usage: None`, updates on second call after worker completes.
