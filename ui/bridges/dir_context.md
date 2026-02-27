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
Role: Primary QML interface exposing core application capabilities.

/DNA/: [call:Slot] -> call:mw.[manager/worker] -> em:Signal -> [update:QML]

- SrcDeps:
  - ui.services.conflict_resolver
  - ui.dialogs.conflicts
  - core.search_worker
  - ui.models.shortcuts
  - core.gio_bridge.desktop
- SysDeps:
  - PySide6.QtCore.QObject, Signal, Property, Slot, QUrl, QMimeData, Qt
  - PySide6.QtWidgets.QMenu
  - PySide6.QtGui.QCursor, QIcon, QDrag
  - pathlib
  - hashlib
  - urllib

API:
  - AppBridge(QObject):
    - cutPaths [Property(list)]
    - targetCellWidth [Property(int)] 
    - searchEngineName [Property(str)]
    - startDrag(paths) -> None: Initiates system drag-and-drop defaulting to MoveAction.
    - handleDrop(urls, dest_dir, mode) -> None: Delegates drop context and action intent to FileManager.
    - openPath(path) -> None: Navigates UI to given path via view manager.
    - showContextMenu(paths) -> None: Displays native desktop QMenu for paths.
    - renameFile(old_path, new_name) -> None: Resolves conflicts and executes rename.
    - startSearch(directory, pattern, recursive) -> None: Triggers Async SearchWorker.
    - cancelSearch() -> None: Stops active search execution.
    - queueSelectionAfterRefresh(paths) -> None: Stages paths for selection post-reload.
    - selectPendingPaths() -> list: Consumes staged paths.
!Caveat: `getThumbnailPath()` is deprecated; thumbnail URL resolution has moved to `RowBuilder._resolve_thumbnail_url()` to avoid blocking I/O on render thread.
