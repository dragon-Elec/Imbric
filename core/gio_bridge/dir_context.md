# Imbric Core: Gio Bridge
Role: Interface layer between Imbric business logic and GNOME/Gio virtual file system (VFS).

## Maintenance Rules
- Gio Specific: All operations must use `gi.repository.Gio`.
- Event Driven: Use signals for state updates from monitors and scanners.

## Atomic Notes (Architectural Truths)
- !Decision: [Gio.Monitor > polling] - Reason: Efficient kernel-level event tracking for local and network mounts.
- !Decision: [Session IDs in Signals] - Reason: Prevents cross-talk; UI ignores results from cancelled or stale scans.
- !Pattern: [Batched Coalescing] - Reason: Buffered emission (100ms) prevents layout thrashing during directory loads.
- !Rule: [Native Non-Blocking] - Reason: Enumeration and metadata fetching must never block the main thread.
- !Pattern: [Lazy Metadata] - Reason: Core listing is fast; dimensions and counts load async via priority workers.
- !Decision: [Cached FS Usage] - Reason: File system capacity checks are blocking; async fetch + cache prevents UI stutter.
- !Rule: [GIO Monitor Priority] - Reason: Use GIO signals for volume/drive changes instead of polling /proc or /dev.

## Sub-Directory Index
- None

## Module Audits

### [FILE: [desktop.py](./desktop.py)] [DONE]
Role: Desktop integration and Sidebar data providers.

/DNA/: [[Path.home() -> GTK Bookmarks -> monitor_file() -> em:bookmarksChanged] + [trash:/// -> monitor_directory() -> _check_trash_task -> em:itemsChanged]]

- SrcDeps: core.utils.gio_qtoast
- SysDeps: gi.repository (Gio, GLib), pathlib.Path, urllib.parse.unquote, PySide6.QtCore (QObject, Signal, Slot, Property)

API:
  - [open_with_default_app()](./desktop.py#L11) -> bool: Launches default URI handler.
  - [BookmarksBridge](./desktop.py#L20)(QObject): Watches GTK bookmarks file.
  - [QuickAccessBridge](./desktop.py#L79)(QObject): Aggregates XDG dirs + Trash status + Bookmarks.

### [FILE: [metadata.py](./metadata.py)] [DONE]
Role: Async metadata extraction workers using GioWorkerPool.

/DNA/: [[path -> ItemCountWorker -> enumerator.next_files(200) -> em:countReady] + [path -> DimensionWorker -> gfile.is_native() -> QImageReader -> em:dimensionsReady]]

- SrcDeps: .metadata_utils, .utils.gio_qtoast
- SysDeps: gi.repository (Gio, GLib), datetime, PySide6.QtCore (QObject, Signal, Slot), PySide6.QtGui (QImageReader)

API:
  - [ItemCountWorker](./metadata.py#L10)(QObject): Counts files (Priority 0).
  - [DimensionWorker](./metadata.py#L55)(QObject): Reads image dimensions (Priority 60).
  - [PropertiesWorker](./metadata.py#L98)(QObject): Full metadata fetch (Priority 80).
!Caveat: DimensionWorker returns (0,0) for non-native URIs to avoid hung threads.

### [FILE: [scanner.py](./scanner.py)] [DONE]
Role: Async Directory Enumeration using Gio.enumerate_children_async.

/DNA/: [scan_directory() -> enumerate_children_async -> _process_batch -> _batch_buffer -> _flush_buffer -> em:filesFound -> [can_thumbnail()? -> worker.enqueue()]]

- SrcDeps: .metadata.ItemCountWorker, .metadata.DimensionWorker
- SysDeps: gi.repository (Gio, GLib, GnomeDesktop), urllib.parse, uuid.uuid4, PySide6.QtCore (QObject, Signal, Slot, QTimer, Property)

API:
  - [DirectoryReader](./scanner.py#L28)(QObject):
    - [scan_directory()](./scanner.py#L136)(path): Async scan with session tracking.
    - [scan_single_file()](./scanner.py#L169)(path): Surgical update for UI.
    - [cancel()](./scanner.py#L191)(): Aborts scan and worker tasks.
!Caveat: childCount initialized to -1 (loading state) for directories.

### [FILE: [volumes.py](./volumes.py)] [DONE]
Role: Wraps Gio.VolumeMonitor with async usage updates.

/DNA/: [[monitor.get_mounts() -> _get_usage() -> _pool.enqueue(_fetch_usage_task) -> em:volumesChanged] + [mount_volume() -> vol.mount() -> em:mountSuccess]]

- SrcDeps: .utils.gio_qtoast
- SysDeps: gi.repository (Gio, GLib), PySide6.QtCore (QObject, Signal, Slot, Property)

API:
  - [VolumesBridge](./volumes.py#L23)(QObject):
    - [get_volumes()](./volumes.py#L73) -> list: Aggregates volumes and active mounts.
    - [mount_volume()](./volumes.py#L121)(identifier): Async mount request.
    - [unmount_volume()](./volumes.py#L134)(identifier): Async unmount request.
!Caveat: Usage stats are lazily loaded and cached; first call returns null/loading.
