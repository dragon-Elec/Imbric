# Imbric/ui/services

Identity: Domain-specific logic controllers that bridge the gap between pure core systems and QML/UI presentation. These services handle stateful UI operations (like conflict resolution memory) and layout math (like RowBuilder) that are too complex for QML.

## Rules
*(Pending user approval)*

## Atomic Notes
*(Pending user approval)*

## Index
*(No sub-directories)*

## Audits

### [FILE: conflict_resolver.py] [DONE]
Role: Stateful helper for resolving file conflicts during batch ops, retaining 'Apply to All' choices.

/DNA/: `[call:resolve() -> if(apply_all_cached) -> return action] + [show(ConflictDialog) -> cache(action) -> return action]`

- SrcDeps:
  - `ui.dialogs.conflicts`
- SysDeps:

API:
  - ConflictResolver:
    - resolve(src, dest) -> tuple[ConflictAction, str]: Resolves copy/move conflicts.
    - resolve_rename(old, new) -> tuple[ConflictAction, str]: Resolves rename conflicts.

### [FILE: properties_logic.py] [DONE]
Role: Coordinates asynchronous metadata extraction for File Properties using QThreadPool.

/DNA/: `[call:request_properties() -> _worker.enqueue() -> wait] + [_worker.propertiesReady -> em:propertiesReady(path, dict)]`

- SrcDeps:
  - `core.gio_bridge.metadata`
  - `core.metadata_utils`
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Signal`
  - `PySide6.QtCore.Slot`

API:
  - PropertiesLogic(QObject):
    - request_properties(path) -> None: Async lookup for single file.
    - request_properties_batch(paths) -> None: Async lookup for multiple.
    - format_size(int) -> str: Bytes to human-readable.

### [FILE: row_builder.py] [DONE]
Role: Justified Grid Layout engine that streams items, calculates scaling/aspects, builds row batches, and pre-renders thumbnail URIs.

/DNA/: `[em:appendFiles -> _calculate_thumbnail_cap -> resolve_url -> _trigger_layout_update] + [QTimer(50) -> _build_rows() -> scale(aspect*ht) -> pack_or_wrap -> em:rowsChanged]`

- SrcDeps:
  - `core.sorter`
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Slot`
  - `PySide6.QtCore.Signal`
  - `PySide6.QtCore.Property`
  - `PySide6.QtCore.QTimer`
  - `hashlib`
  - `urllib.parse`
  - `pathlib.Path`
  - `gi.repository.GLib`

API:
  - RowBuilder(QObject):
    - appendFiles(list) -> None: Streams new files into layout.
    - addSingleItem(dict) / removeSingleItem(str) -> None: Surgical updates.
    - setRowHeight(int) / setAvailableWidth(int) -> None: Triggers re-layout.
    - getItemsInRect(x, y, w, h) -> list: Calculates intersection for marquee selection.

!Caveat: `_resolve_thumbnail_url` directly checks `~/.cache/thumbnails/large/` via MD5 to skip blocking standard thumbnailer calls when cached.
!Caveat: Layout updates are debounced by 50ms via `_layout_timer` to prevent UI freezing during streaming loads.
