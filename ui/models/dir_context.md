Identity: Data structures, ViewModel components, and Python models (e.g. QAbstractListModel) holding UI state to feed directly to QML Views.

Rules:
- Must only expose pure data and read-only state via QProperties.
- UI models should reflect underlying system state, not execute heavy I/O directly.
- Ensure bridging interactions remain asynchronous to prevent UI freezing.

Atomic Notes:
- `!Pattern: [Surgical Updates > Full Refresh] - Reason: PaneContexts listen to the global FileMonitor to surgically update their RowBuilder (add/remove single rows) instead of triggering expensive full re-scans.`
- `!Rule: [Isolated Panes] - Reason: Every PaneContext spawns its own Scanner, RowBuilder, and AppBridge, isolating state and preventing cross-pane data corruption.`

Index: None

---

### [FILE: shortcuts.py] [DONE]
Role: Pure data model for managing keyboard shortcut configurations via QSettings.

/DNA/: [call:set()] -> update:dict -> call:save() -> QSettings.setValue -> em:configChanged

- SrcDeps:
  - None
- SysDeps:
  - PySide6.QtCore.QObject, Signal, QSettings
  - enum.Enum, auto
  - typing.Dict, Optional

API:
  - ShortcutAction(Enum): Defines mapping identifiers. 
  - Shortcuts(QObject):
    - get(action) -> str: Retrieves assigned key sequence.
    - set(action, key_sequence) -> None: Updates binds and persists to disk.
    - reset(action=None) -> None: Reverts specific or all mappings to default.
    - get_conflicts() -> Dict[str, list]: Identifies duplicate shortcut assignments.

---

### [FILE: sidebar_model.py] [DONE]
Role: Nested QAbstractListModel providing sidebar sections and items (Volumes and Bookmarks) to QML to prevent UI flickering.

/DNA/: [call:update_section_items] -> beginResetModel(inner) -> _items = [] -> endResetModel(inner) -> [em:dataChanged]

- SrcDeps:
  - core.gio_bridge.desktop.BookmarksBridge
  - core.gio_bridge.volumes.VolumesBridge
- SysDeps:
  - PySide6.QtCore.QAbstractListModel, Qt, Slot, Signal, QModelIndex, Property

API:
  - SectionItemsModel(QAbstractListModel):
    - update_items(new_items) -> None: Replaces the internal list via reset model, triggering localized UI redraws.
  - SidebarModel(QAbstractListModel):
    - update_section_items(title, items) -> None: Finds the section and passes the update to its inner `SectionItemsModel`.
    - set_section_collapsed(title, is_collapsed) -> None: Persists section toggling state.

---

### [FILE: pane_context.py] [DONE]
Role: State engine for a single view context (Pane), holding its dedicated Scanner, RowBuilder, and Bridge.

/DNA/: [call:navigate_to -> call:scanner.scan_directory -> em:filesFound] + [em:file_monitor.fileCreated -> if(current_path) -> call:scanner.scan_single_file] + [em:scanFinished -> bridge.selectPendingPaths] => [update:row_builder]

- SrcDeps:
  - core.gio_bridge.scanner.FileScanner
  - ui.services.row_builder.RowBuilder
  - ui.bridges.app_bridge.AppBridge
- SysDeps:
  - PySide6.QtCore.QObject, Signal, Slot, Property
  - pathlib.Path
  - gi.repository.Gio

API:
  - PaneContext(QObject):
    - currentPath [Property(str)]: The path this pane currently displays.
    - pathSegments [Property(QVariantList)]: Dynamic breadcrumb models mapping segments to path resolution logic with virtual future path retention.
    - selection [Property(list)]: Paths currently selected by QML in this pane.
    - canGoBack, canGoForward, canGoUp [Property(bool)]: Exposes navigation stack states to QML bindings.
    - navigate_to(path) -> None: Triggers directory scan and updates navigation stacks. If path is invalid, emits `pathRejected`.
    - go_back(), go_forward(), go_home() -> None: Modifies history stack and triggers navigation logic, maintaining Nemo-style virtual path retention.
    - updateSelection(paths) -> None: Receives selected paths from QML view.
    - selectPathsRequested(list) [Signal]: Emitted to force QML selection (e.g. after refresh).
    - change_zoom(direction) -> None: Modifies RowBuilder's height settings.
    - cleanup() -> None: Stops scanners and disconnects global signals on close.

---

### [FILE: tab_model.py] [DONE]
Role: QAbstractListModel managing the collection of open PaneContexts for the tab bar.

/DNA/: [call:add_tab] -> beginInsertRows -> instantiate:PaneContext -> connect:pathChanged -> endInsertRows

- SrcDeps:
  - ui.models.pane_context.PaneContext
- SysDeps:
  - PySide6.QtCore.QAbstractListModel, Qt, QModelIndex, QByteArray
  - gi.repository.Gio

API:
  - TabListModel(QAbstractListModel):
    - add_tab(path) -> PaneContext: Instantiates a new pane context and starts navigation.
    - remove_tab(index) -> None: Disposes of pane context and its resources.
    - get_tab(index) -> PaneContext: Retrieves instance for programmatic access.

---

### [FILE: context_menu_model.py] [DONE]
Role: ViewModel handling state, data formatting, and action execution for Gtk-mimic context menus.

/DNA/: [call:getModelForPaths(paths)] -> if(!paths) -> [build_bg_model] else -> [build_file_model] => list(dict) + [call:executeAction(id, paths)] -> am.get_action(id).trigger()

- SrcDeps:
  - ui.models.shortcuts.ShortcutAction
- SysDeps:
  - PySide6.QtCore.QObject, Slot

API:
  - ContextMenuViewModel(QObject):
    - getModelForPaths(paths) -> list: Generates list of action objects for GtkMenu.
    - executeAction(action_id, paths) -> void: Triggers the corresponding QAction.
