Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/core/backends/gio — GIO concrete implementations of IOBackend, ScannerBackend, MetadataProvider, FileMonitor, and VolumesBridge.

!Rule: [gi.require_version before every gi import] - Reason: Missing require_version silently uses wrong GLib version; causes hard-to-trace runtime errors.
!Decision: [Gio.Cancellable injected per-job] - Reason: Shared cancellables cause cross-job cancellation; each FileJob gets a fresh Gio.Cancellable in `GIOBackend._submit`.
!Pattern: [Runnable per operation] - Reason: All I/O runs in QThreadPool via QRunnable subclasses; GIOBackend._submit wraps any runnable class and injects cancellable.

Index:
- helpers.py — Path/URI utility functions (_make_gfile, ensure_uri, to_unix_timestamp).
- backend.py — GIOBackend (IOBackend) + GIOMetadataProvider (MetadataProvider).
- io_ops.py — QRunnable subclasses for copy/move/batch/rename/create/symlink.
- trash_ops.py — QRunnable subclasses for trash/restore/list_trash/empty_trash.
- scanner.py — FileScanner (ScannerBackend) for async directory enumeration.
- metadata.py — Synchronous `get_file_info()` function + attributes constants.
- metadata_workers.py — QObject workers for dimensions, item counts, and batch processing.
- monitor.py — FileMonitor (GIO directory watcher with debounce).
- volumes.py — VolumesBridge (VolumeMonitor wrapper with async usage cache).
- desktop.py — Desktop integration: recent files, bookmarks, app launchers, breadcrumbs.

---

### [FILE: helpers.py] [USABLE]
Role: Shared GIO path/URI construction helpers. Imported across all gio sub-files.

/DNA/: `_make_gfile(path_or_uri)` => Gio.File.new_for_uri if "://" in str else new_for_path; `ensure_uri` -> commandline_arg parse => canonical URI.

- SysDeps: gi.repository{Gio}

API:
  - _make_gfile(path_or_uri: str) -> Gio.File
  - _gfile_path(gfile: Gio.File) -> str: get_path() or get_uri()
  - ensure_uri(path_or_uri: str) -> str
  - to_unix_timestamp(dt) -> int: GLib.DateTime -> int, 0 on None/error

---

### [FILE: backend.py] [USABLE]
Role: GIOBackend implements IOBackend; GIOMetadataProvider implements MetadataProvider. Both delegate to low-level runnables/functions.

/DNA/: `GIOBackend._submit(job, RunClass)` -> if()!job.cancellable: assign Gio.Cancellable -> `RunClass(job, signals)` -> pool.start -> return job.id

- SrcDeps: .io_ops, .trash_ops, .scanner, .metadata, .helpers, core.interfaces{IOBackend, ScannerBackend, MetadataProvider}, core.models{FileJob, FileInfo}
- SysDeps: PySide6{QtCore}, gi.repository{Gio}

API:
  - GIOBackend(IOBackend):
    - set_signals(signals) -> None: injects global signal hub.
    - copy(job), move(job), batch_transfer(job), trash(job), restore(job), list_trash(job), empty_trash(job) -> str
    - delete(job) -> str: alias for trash
    - create_folder(job), create_file(job), rename(job), create_symlink(job) -> str
    - query_exists(path) -> bool: _make_gfile(path).query_exists(None)
    - is_same_file(path_a, path_b) -> bool: _make_gfile(a).equal(_make_gfile(b))

  - GIOMetadataProvider(MetadataProvider):
    - get_file_info(path_or_uri, attributes=None) -> FileInfo | None: calls metadata.get_file_info
    - get_dimensions(...) -> None: always None; dimensions handled async by DimensionWorker
    - get_item_count(...) -> -1: always -1; count handled async by ItemCountWorker

!Caveat: `delete()` falls through to `trash()`; no permanent-delete runnable.

---

### [FILE: io_ops.py] [USABLE]
Role: QRunnable implementations for GIO file operations (Copy, Move, Rename, Create).

/DNA/: `GIOOperationRunnable` base -> `emit_started`, `emit_finished`, `_handle_gio_error`; `BatchTransferRunnable.run()` -> loop items -> `_perform_single_transfer` -> `_recursive_transfer` [if dir or cross-vfs move] -> `Gio.File.copy/move/delete`; `TransferRunnable` [single item version]; `RenameRunnable` -> `set_display_name`.

- SrcDeps: core.models.file_job, .helpers, .metadata, core.utils.path_ops
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}, time

API:
  - GIOOperationRunnable(QRunnable):
    - emit_started(), emit_progress(current, total), emit_finished(success, message)
  - BatchTransferRunnable(GIOOperationRunnable):
    - run() -> None: sequential processing of item list
  - TransferRunnable(GIOOperationRunnable):
    - run() -> None: unified copy/move/recursive logic
  - RenameRunnable(GIOOperationRunnable):
    - run() -> None: uses set_display_name
  - CreateFolderRunnable(GIOOperationRunnable):
    - run() -> None
  - CreateFileRunnable(GIOOperationRunnable):
    - run() -> None
  - CreateSymlinkRunnable(GIOOperationRunnable):
    - run() -> None

---

### [FILE: trash_ops.py] [USABLE]
Role: QRunnable implementations for GIO trash operations (Trash, Restore, List, Empty).

/DNA/: `SendToTrashRunnable` -> `gfile.trash()`; `RestoreFromTrashRunnable` -> `enumerate_children("trash:///")` -> find latest match by `trash::orig-path` -> `trash_file.move(dest_path)`; `ListTrashRunnable` -> `_list_trash()` -> populate `TrashItem` list -> `em:itemListed`; `EmptyTrashRunnable` -> `enumerate_children("trash:///")` -> `child.delete()` [with recursion for non-empty folders].

- SrcDeps: .io_ops, .helpers, core.models{file_job, trash_item}, core.utils.path_ops
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}, typing

API:
  - SendToTrashRunnable(GIOOperationRunnable):
    - run() -> None: uses gfile.trash
  - RestoreFromTrashRunnable(GIOOperationRunnable):
    - run() -> None: scans trash:/// for candidate -> moves back
  - ListTrashRunnable(GIOOperationRunnable):
    - run() -> None: emits TrashItem objects
  - EmptyTrashRunnable(GIOOperationRunnable):
    - run() -> None: recursively deletes everything in trash:///

---

### [FILE: scanner.py] [USABLE]
Role: Async directory scanner using GIO. Offloads batch processing to `BatchProcessorWorker`.

/DNA/: `scan_directory(path)` -> `enumerate_children_async` -> `_on_enumerate_ready` -> `_fetch_next_batch` -> `next_files_async` -> `_on_batch_ready` -> `batch_processor.enqueue` -> `_on_batch_processed` -> `_batch_buffer.extend` -> `_emit_timer.start` -> `timeout` -> `_flush_buffer` -> `em:filesFound`.

- SrcDeps: .helpers, .metadata_workers
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}, uuid

API:
  - FileScanner(QObject):
    - scan_directory(path: str) -> None (slot)
    - scan_single_file(path: str) -> None (slot)
    - cancel() -> None (slot)
    - setShowHidden(show: bool) -> None (slot)
    - showHidden() -> bool (slot)
    - current_path() -> str (property)
    - set_workers(count_worker, dimension_worker) -> None
    Signals: filesFound(session_id, list), scanFinished(session_id), scanError(error), fileAttributeUpdated(path, key, val)

---

### [FILE: metadata.py] [USABLE]
Role: Synchronous GIO-specific metadata extraction functions.

/DNA/: `get_file_info(path, attributes)` -> `Gio.File.query_info(attributes)` -> extract names, size, times, icons, permissions -> `FileInfo(...)` => populated FileInfo object.

- SrcDeps: core.models.file_info, core.utils.formatting, .helpers
- SysDeps: gi.repository{Gio, GLib}

API:
  - resolve_mime_icon(gfile: Gio.File, cancellable=None) -> str
  - get_file_info(path_or_uri: str, attributes=ATTRS_FULL) -> FileInfo | None

---

### [FILE: metadata_workers.py] [USABLE]
Role: QObject background workers for directory counting, image dimensions, file properties, existence, and scanner batch processing.

/DNA/: `ItemCountWorker.enqueue(path)` -> `AsyncWorkerPool` run `_count` [blocking iterator]; `DimensionWorker.enqueue(path)` -> `QImageReader` read [local] or `FileInfo` follow target -> `QImageReader`; `BatchProcessorWorker.enqueue(file_infos)` -> `_process_background` [convert Gio.FileInfo list to dict list with MIME/thumbnail metadata].

- SrcDeps: core.threading.worker_pool, .metadata, .helpers, core.utils.path_ops
- SysDeps: gi.repository{Gio, GLib, GnomeDesktop}, PySide6{QtCore, QtGui}, datetime

API:
  - ItemCountWorker(QObject):
    - enqueue(uri, path) -> None (slot)
    - clear() -> None (slot)
    Signals: countReady(path, count)
  - DimensionWorker(QObject):
    - enqueue(uri, path) -> None (slot)
  - PropertiesWorker(QObject):
    - enqueue(path) -> None (slot)
    - enqueue_batch(paths) -> None (slot)
  - ExistenceWorker(QObject):
    - enqueue(task_id, path) -> None (slot)
  - UniqueNameWorker(QObject):
    - enqueue(task_id, dest_path, style="copy") -> None (slot)
  - BatchProcessorWorker(QObject):
    - enqueue(session_id, file_infos, parent_uri, show_hidden, is_native) -> None (slot)
    Signals: batchProcessed(session_id, list), allTasksDone(session_id)

---

### [FILE: monitor.py] [USABLE]
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
    - stop() -> None (slot)

!Caveat: `watch` silently returns (no-op) for `recent://` and `trash://` paths.

---

### [FILE: volumes.py] [USABLE]
Role: Wraps Gio.VolumeMonitor; provides cached volume list with lazy async disk-usage injection.

/DNA/: `__init__` -> connect monitor signals -> `_rebuild_cache_async` -> pool.enqueue("volumes_rebuild", _build_volume_list_task) [bg: iterate mounts/volumes] -> resultReady -> _cached_volumes = result -> em:volumesChanged; `get_volumes()` -> for each mounted: _get_usage(path) -> if cached: inject usage | else: pool.enqueue(_fetch_usage_task) -> on result: _usage_cache[path] = result -> em:volumesChanged

- SrcDeps: core.threading.worker_pool
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}

API:
  - VolumesBridge(QObject):
    Signals: volumesChanged(), mountSuccess(ident), mountError(message)
    Properties (constant): title="Devices", icon="hard_drive"
    - title() -> str (property)
    - icon() -> str (property)
    - get_icon_name(path) -> str
    - get_volumes() -> list[dict]
    - mount_volume(identifier: str) -> None (slot)
    - unmount_volume(identifier: str) -> None (slot)

!Caveat: Usage is lazily fetched at `get_volumes()` call time.

---

### [FILE: desktop.py] [USABLE]
Role: GIO Desktop integration (XDG dirs, bookmarks, MIME, breadcrumbs).

/DNA/: `get_special_dirs()` -> cache XDG paths; `get_breadcrumb_segments(path)` -> loop `curr.get_parent()` -> check `find_enclosing_mount` for mount names/icons; `BookmarksBridge` -> monitor `~/.config/gtk-3.0/bookmarks` -> `_resolve_task` [read/parse file] -> `em:bookmarksChanged`; `QuickAccessBridge` -> aggregate XDG + Bookmarks + Trash [monitor `trash:///` item-count].

- SrcDeps: core.threading.worker_pool, .helpers
- SysDeps: gi.repository{Gio, GLib}, PySide6{QtCore}, pathlib

API:
  - open_with_default_app(path: str) -> bool
  - get_special_dirs() -> dict
  - resolve_identity(raw_path: str) -> str
  - get_breadcrumb_segments(path: str, active_path: str, fast_mode: bool = False) -> list
  - enrich_breadcrumbs(virtual_path: str, active_path: str) -> list
  - create_desktop_mime_data(paths: list, is_cut: bool) -> QMimeData
  - BookmarksBridge(QObject):
    - get_bookmarks() -> list (slot)
  - QuickAccessBridge(QObject):
    - title() -> str (property)
    - icon() -> str (property)
    - get_items() -> list (slot)
    Signals: itemsChanged()
