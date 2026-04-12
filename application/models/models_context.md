Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/application/models
Data structures, ViewModel components, and Python models (e.g. QAbstractListModel) holding UI state to feed directly to QML Views.

Rules:
- Must only expose pure data and read-only state via `QProperties`.
- UI models should reflect underlying system state, not execute heavy I/O directly.
- Ensure bridging interactions remain asynchronous to prevent UI freezing.

Atomic Notes:
!Pattern: [Surgical Updates > Full Refresh] - Reason: PaneContexts listen to the global FileMonitor to surgically update their RowBuilder (add/remove single rows) instead of triggering expensive full re-scans.
!Rule: [Isolated Panes] - Reason: Every PaneContext spawns its own Scanner, RowBuilder, and AppBridge, isolating state and preventing cross-pane data corruption.

Index: None

---

### [FILE: shortcuts.py] [USABLE]
Role: Pure data model for managing keyboard shortcut configurations via QSettings.

/DNA/: [call:set()] -> update:dict -> call:save() -> QSettings.setValue -> em:configChanged

- SrcDeps: None
- SysDeps: PySide6.QtCore{QObject, Signal, QSettings}, enum{Enum, auto}, typing

API:
  - ShortcutAction(Enum): Defines mapping identifiers. 
  - Shortcuts(QObject):
    - get(action: ShortcutAction) -> str: Retrieves assigned key sequence.
    - set(action: ShortcutAction, key_sequence: str) -> void: Updates binds and persists to disk.
    - reset(action: ShortcutAction|None) -> void: Reverts specific or all mappings to default.
    - get_conflicts() -> dict: Identifies duplicate shortcut assignments.

---

### [FILE: sidebar_model.py] [USABLE]
Role: Nested QAbstractListModel providing sidebar sections and items (Volumes and Bookmarks) to QML to prevent UI flickering.

/DNA/: [call:update_section_items] -> beginResetModel(inner) -> _items = [] -> endResetModel(inner) -> [em:dataChanged]

- SrcDeps: None
- SysDeps: PySide6.QtCore{QAbstractListModel, Qt, Slot, Signal, QModelIndex, Property}

API:
  - SectionItemsModel(QAbstractListModel):
    - update_items(new_items: list) -> void: Replaces the internal list via reset model.
    - Inherits: QAbstractListModel{rowCount, data, roleNames}
  - SidebarModel(QAbstractListModel):
    - update_section_items(title: str, items: list) -> void: Finds the section and passes the update to its inner SectionItemsModel.
    - set_section_collapsed(title: str, is_collapsed: bool) -> void: Updates and emits dataChanged for the section.
    - Inherits: QAbstractListModel{rowCount, data, roleNames}

---

### [FILE: row_model.py] [USABLE]
Role: QAbstractListModel wrapping RowBuilder's row data for incremental QML updates.

/DNA/: `setRows(rows)` -> beginResetModel -> _rows = rows -> endResetModel; `appendRows(new_rows)` -> beginInsertRows -> _rows.extend -> endInsertRows

- SrcDeps: None
- SysDeps: PySide6.QtCore{QAbstractListModel, Qt, Slot}

API:
  - RowModel(QAbstractListModel):
    - setRows(rows: list[list[dict]]) -> None: Replaces all rows (model reset).
    - appendRows(new_rows: list[list[dict]]) -> None: Appends rows incrementally.
    - clear() -> None: Removes all rows.
    - getRow(index: int) -> list: [Slot] Returns single row by index.
    - getRowCount() -> int: [Slot] Returns total row count.
    - getAllItems() -> list: [Slot] Flattens all rows into item list.
    - Roles: rowData (Qt.UserRole + 1)

!Caveat: `appendRows` is only useful for appending to an existing model. Justified layout requires full rebuild when items are inserted mid-stream, so `setRows` is used in practice.

---

### [FILE: pane_context.py] [USABLE]
Role: State engine for a single view context (Pane), holding its dedicated Scanner, RowBuilder, and Bridge.

/DNA/: [call:navigate_to -> call:scanner.scan_directory -> em:filesFound] + [em:file_monitor.fileCreated -> if(current_path) -> call:scanner.scan_single_file] + [em:scanFinished -> bridge.selectPendingPaths] => [update:row_builder]

- SrcDeps: .services.row_builder.RowBuilder, .bridges.app_bridge.AppBridge, core.threading.worker_pool.AsyncWorkerPool, core.backends.gio.{scanner.FileScanner, desktop}
- SysDeps: PySide6.QtCore{QObject, Signal, Slot, Property}, gi.repository.{Gio, GLib}, pathlib.Path

API:
  - PaneContext(QObject):
    - currentPath() / current_path() -> str: [Property/Setter] The path this pane currently displays.
    - pathSegments() -> list: [Property] Breadcrumb models mapping segments to path resolution.
    - selection() -> list: [Property] Paths currently selected by QML in this pane.
    - canGoBack() / canGoForward() / canGoUp() -> bool: [Property] History state status.
    - fileScanner() / rowBuilder() / appBridge() -> QObject: [Property] Exposes core components to QML.
    - navigate_to(path: str) -> void: Triggers scan and updates history.
    - go_up() / go_back() / go_forward() / go_home() -> void: Navigation logic.
    - change_zoom(direction: int) -> void: Adjusts RowBuilder's height settings.
    - scan_current() -> void: Re-scans the current directory using current scanner session.
    - updateSelection(paths: list) -> void: [Slot] Syncs selection from QML view.
    - cleanup() -> void: Disconnects global monitor signals and cancels scanners.

---

### [FILE: tab_model.py] [USABLE]
Role: QAbstractListModel managing the collection of open PaneContexts for the tab bar.

/DNA/: [call:add_tab] -> beginInsertRows -> instantiate:PaneContext -> connect:pathChanged -> endInsertRows

- SrcDeps: .pane_context.PaneContext
- SysDeps: PySide6.QtCore{QAbstractListModel, Qt, QModelIndex, QByteArray}, gi.repository.Gio

API:
  - TabListModel(QAbstractListModel):
    - add_tab(path: str|None) -> PaneContext: Instantiates a new pane context and starts navigation.
    - remove_tab(index: int) -> void: Disposes of pane context and resources.
    - get_tab(index: int) -> PaneContext | None: [Slot] Retrieves instance for programmatic access.
    - Inherits: QAbstractListModel{rowCount, data, roleNames}

---

### [FILE: context_menu_model.py] [USABLE]
Role: ViewModel handling state, data formatting, and action execution for Gtk-mimic context menus. Includes Sort By submenu with live state sync.

/DNA/: [call:getModelForPaths(paths)] -> if(!paths) -> [build_bg_model + sort_submenu] else -> [build_file_model] => list(dict) + [call:executeAction(id, paths)] -> if(SORT_*) -> call:sorter.set* | else -> am.get_action(id).trigger()

- SrcDeps: .shortcuts.ShortcutAction, application.services.sorter.SortKey, core.backends.gio.desktop.open_with_default_app
- SysDeps: PySide6.QtCore{QObject, Slot}

API:
  - ContextMenuViewModel(QObject):
    - getModelForPaths(paths: list) -> list: [Slot] Generates list of action objects for GtkMenu.
    - executeAction(action_id: str, paths: list) -> void: [Slot] Triggers QAction, native open, or sort config change.
    - _get_current_sorter() -> Sorter | None: Resolves active pane's Sorter via ShellManager.
    - _build_sort_submenu() -> list: Builds Sort By submenu with checkmarks for current state.
