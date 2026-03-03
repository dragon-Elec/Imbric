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

### [FILE: app_bridge.py] [DONE]
Role: Primary QML interface exposing core application capabilities and bridging UI actions to managers.

/DNA/: [call:Slot -> call:mw.(manager/worker) -> em:Signal -> update:QML] + [mw.clipboard.em:changed -> em:cutPathsChanged -> Property:cutPaths] + [call:startSearch -> SearchWorker.exec -> em:searchResultsFound]

- SrcDeps:
  - ui.widgets.drag_helper.start_drag_session
  - ui.services.conflict_resolver.ConflictResolver
  - ui.dialogs.conflicts.ConflictAction
  - core.search_worker.SearchWorker
- SysDeps:
  - PySide6.QtCore.QObject, Signal, Property, Slot, Qt
  - PySide6.QtGui.QCursor, QIcon
  - gi.repository.Gio

API:
  - AppBridge(QObject):
    - cutPaths [Property(list)]: Returns list of paths in cut state from FileManager.
    - targetCellWidth [Property(int)]: Controls thumbnail grid spacing.
    - searchEngineName [Property(str)]: Identifies active search backend (fd/scandir).
    - startDrag(paths) -> None: Initiates system drag via DragHelper utility.
    - handleDrop(urls, dest_dir, mode) -> None: Delegates drop intent and action to FileManager.
    - openPath(path) -> None: Navigates UI to given path via main window.
    - showContextMenu(paths) -> None: Emits `requestContextMenu(paths)` signal; menu implementation decoupled to QML.
    - showBackgroundContextMenu() -> None: Emits `requestContextMenu([])` signal.
    - renameFile(old_path, new_name) -> None: Resolves conflicts and executes rename via file_ops.
    - paste() -> None: Triggers paste_to_current in FileManager.
    - startSearch(dir, pattern, recursive) -> None: Starts background SearchWorker.
    - cancelSearch() -> None: Stops active search.
    - zoom(delta) -> None: Delegates zoom_in/out to view_manager.
    - queueSelectionAfterRefresh(paths) -> None: Stages paths for selection after next directory reload.
    - selectPendingPaths() -> list: Consumes and clears the staged selection queue.
!Caveat: `getThumbnailPath()` is deprecated; thumbnail URL resolution has moved to `RowBuilder._resolve_thumbnail_url()` to avoid blocking I/O on render thread.
