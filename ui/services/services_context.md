# Imbric/ui/services

Identity: Domain-specific logic controllers that bridge the gap between pure core systems and QML/UI presentation. These services handle stateful UI operations (like conflict resolution memory) and layout math (like RowBuilder) that are too complex for QML.

## Rules
*(Pending user approval)*

## Atomic Notes
*(Pending user approval)*

## Index
*(No sub-directories)*

## Audits

### [FILE: conflict_resolver.py] [USABLE]
Role: Stateful helper for resolving file conflicts during batch ops, retaining 'Apply to All' choices.

/DNA/: `[call:resolve() -> if(apply_all_cached) -> return action] + [show(ConflictDialog) -> cache(action) -> return action]`

- SrcDeps: ui.dialogs.conflicts
- SysDeps: PySide6{QtCore}, threading

API:
  - ConflictResolver(QObject):
    - resolve(src, dest) -> tuple[ConflictAction, str]: Resolves copy/move conflicts.
    - resolve_rename(old, new) -> tuple[ConflictAction, str]: Resolves rename conflicts.
    - __call__(src, dest) -> tuple[ConflictAction, str]: Direct call alias for resolve.

### [FILE: properties_logic.py] [USABLE]
Role: Coordinates asynchronous metadata extraction for File Properties using QThreadPool.

/DNA/: `[call:request_properties() -> _worker.enqueue() -> wait] + [_worker.propertiesReady -> em:propertiesReady(path, dict)]`

- SrcDeps: core.backends.gio.metadata_workers, core.utils.formatting
- SysDeps: PySide6{QtCore}

API:
  - PropertiesLogic(QObject):
    - request_properties(path) -> None: Async lookup for single file.
    - request_properties_batch(paths) -> None: Async lookup for multiple.
    - format_size(int) -> str: Bytes to human-readable.

### [FILE: row_builder.py] [USABLE]
Role: Justified Grid Layout engine that streams items, calculates scaling/aspects, builds row batches, and pre-renders thumbnail URIs.

/DNA/: `[em:appendFiles -> _calculate_thumbnail_cap -> _resolve_thumbnail_url -> _trigger_layout_update] + [QTimer(50) -> _build_rows() -> scale(aspect*ht) -> pack_or_wrap -> em:rowsChanged]`

- SrcDeps: ui.services.sorter, ui.services.view_config, ui.models.row_model
- SysDeps: PySide6{QtCore}, hashlib, urllib.parse, pathlib, gi.repository.GLib

API:
  - RowBuilder(QObject):
    - appendFiles(list) -> None: Streams new files into layout.
    - addSingleItem(dict) / removeSingleItem(str) -> None: Surgical updates.
    - setRowHeight(int) / setAvailableWidth(int) -> None: Triggers re-layout.
    - getItemsInRect(x, y, w, h) -> list: Calculates intersection for marquee selection.
    - getItemsInRange(start, end) -> list: Path list for row range.
    - setFiles(list) / finishLoading() -> None: Navigation state management.
    - clear() -> None: Resets layout.
    - updateItem(path, attr, value) -> None: Single item state update.
    - calculate_next_zoom_height(direction) -> int: Snap height calculation.
    - getRows() -> list: Row data structure.
    - getRowHeight() -> int / getSorter() -> Sorter: Accessors.
    - getAllItems() -> list: Flattened sorted items.
    - Properties: rowHeight(int), sorter(Sorter), spacing(int), footerHeight(int).

!Caveat: `_resolve_thumbnail_url` directly checks `~/.cache/thumbnails/large/` via MD5 to skip blocking standard thumbnailer calls when cached.
!Caveat: Layout updates are debounced by 50ms via `_layout_timer` to prevent UI freezing during streaming loads.
!Caveat: Uses `RowModel` (QAbstractListModel) for incremental QML updates — no full model replacement on every change.

---

### [FILE: sorter.py] [USABLE]
Role: QML-exposed file list sorter with natural sort, folders-first, and sort-direction state.

/DNA/: `sort(files, key?, asc?)` -> [if folders_first: split dirs/files -> each.sort(key) -> rejoin | else: list.sort(key)] => sorted list; `setKey()/setAscending()/setFoldersFirst()` -> if changed: em:sortChanged

- SysDeps: PySide6{QtCore}, enum, re

API:
  - SortKey(IntEnum): NAME=0, DATE_MODIFIED=1, SIZE=2, TYPE=3

  - Sorter(QObject):
    Signals: sortChanged()
    Properties: key (int), ascending (bool), foldersFirst (bool)
    - sort(files: list[dict], key=None, ascending=None) -> list[dict]
    - setKey(key: int) -> None
    - setAscending(ascending: bool) -> None
    - setFoldersFirst(enabled: bool) -> None
    - currentKey() -> int: returns current SortKey value.
    - isAscending() -> bool: returns current sort direction.
    - isFoldersFirst() -> bool: returns current folders-first preference.

!Caveat: `sort()` operates on list[dict] (QML JSON model dicts), not `FileInfo` objects. Keys accessed: `isDir`, `name`, `dateModified`, `size`.

---

### [FILE: view_config.py] [USABLE]
Role: Resolves PathCapabilities from core into presentation defaults (sort key, direction, thumbnail strategy).

/DNA/: `resolve(caps)` -> [lookup _CONFIGS by scheme] => ViewConfig | fallback to "file" preset

- SrcDeps: ui.services.sorter
- SysDeps: dataclasses

API:
  - ViewConfig(dataclass, frozen):
    - default_sort_key: SortKey
    - default_ascending: bool
    - folders_first: bool
    - skip_thumbnail_precompute: bool
    - use_streaming_layout: bool
  - resolve(path_caps) -> ViewConfig

!Caveat: `recent://` preset disables folders-first (meaningless for scattered files) and sorts by date desc.
!Caveat: Unknown schemes fall back to the "file" preset (name asc, folders first).
