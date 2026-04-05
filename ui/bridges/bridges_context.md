Identity: Dedicated boundary classes for secure communication between QML and Python logic.

Rules:
- Must only contain `QObject` classes exposed to QML via Signals, Slots, and Properties.
- Should avoid heavy I/O operations directly on the main thread (delegate to workers or core).
- Never hold large UI state here; query `main_window` or managers instead.

Atomic Notes:
- `!Rule: [Delegation > Implementation] - Reason: Bridge methods should route commands to managers/workers instead of implementing core logic directly.`
- `!Pattern: [QObject Signal Sync] - Reason: Use Qt Signals to asynchronously notify QML of state changes rather than blocking.`

Index: None

---

### [FILE: app_bridge.py] [USABLE]
Role: Primary QML interface exposing core application capabilities and bridging UI actions to managers.

/DNA/: [call:Slot -> call:mw.(manager/worker) -> em:Signal -> update:QML] + [mw.clipboard.em:changed -> em:cutPathsChanged -> Property:cutPaths] + [call:startSearch -> SearchWorker.exec -> em:searchResultsFound]

- SrcDeps: .widgets.drag_helper, .services.conflict_resolver, .dialogs.conflicts, core.services.search.worker, core.threading.worker_pool
- SysDeps: PySide6{QtCore, QtGui}, gi.repository.Gio, pathlib, os, hashlib, urllib.parse

API:
  - AppBridge(QObject):
    - cutPaths() -> list: [Property] Returns list of paths in cut state from FileManager.
    - targetCellWidth() -> int: [Property/Setter] Controls thumbnail grid spacing.
    - searchEngineName() -> str: [Property] Identifies active search backend (fd/scandir).
    - startDrag(paths) -> void: Initiates system drag via DragHelper utility.
    - handleDrop(urls, dest_dir, mode) -> void: Delegates drop intent and action to FileManager.
    - openPath(path) -> void: Navigates UI to given path via main window.
    - showContextMenu(paths) -> void: Emits requestContextMenu(paths) signal; menu implementation decoupled to QML.
    - showBackgroundContextMenu() -> void: Emits requestContextMenu([]) signal.
    - renameFile(old_path, new_name) -> void: Resolves conflicts and executes rename via file_ops.
    - paste() -> void: Triggers paste_to_current in FileManager.
    - startSearch(dir, pattern, recursive) -> void: Starts background SearchWorker.
    - cancelSearch() -> void: Stops active search.
    - zoom(delta) -> void: Delegates zoom_in/out to view_manager.
    - queueSelectionAfterRefresh(paths) -> void: Stages paths for selection after next directory refresh.
    - selectPendingPaths() -> list: Consumes and clears the staged selection queue.
!Caveat: getThumbnailPath() is deprecated; thumbnail URL resolution has moved to RowBuilder._resolve_thumbnail_url() to avoid blocking I/O on render thread.
