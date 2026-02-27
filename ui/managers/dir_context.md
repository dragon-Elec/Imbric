# Imbric/ui/managers

Identity: Routing layer for high-level UI coordination. Managers sit above the bridges and models to provide application-wide state (clipboard, navigation stacks, shell structure) and coordinate operations across tabs and core services.

## Rules
*(Pending user approval)*

## Atomic Notes
*(Pending user approval)*

## Index
*(No sub-directories)*

## Audits

### [FILE: action_manager.py] [DONE]
Role: Dynamically constructs and registers all global `QAction` objects from the `Shortcuts` model.

/DNA/: `[loop: bindings.items() -> call:_create_action() -> setShortcut(model) -> connect(slot) -> window.addAction()]`

- SrcDeps:
  - `ui.models.shortcuts`
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Qt`
  - `PySide6.QtGui.QAction`
  - `PySide6.QtGui.QKeySequence`
  - `PySide6.QtGui.QIcon`
  - `PySide6.QtWidgets.QWidget`

API:
  - ActionManager(QObject):
    - setup_actions(...) -> None: Binds all shortcuts to manager methods.
    - get_action(enum_id) -> Optional[QAction]: Retrieves a specific standard action.

### [FILE: file_manager.py] [DONE]
Role: Consolidates clipboard state, file action dispatch (trash, rename, duplicate), and drag/drop handling.

/DNA/: `[action_slot() -> _get_selection() -> mw.transaction_manager/file_ops] + [_set_clipboard(paths, is_cut) -> GNOME_COPIED_FILES mime -> em:clipboardChanged] + [handle_drop() -> batchTransfer(mode)] + [_run_transfer() -> ConflictResolver callback -> batchTransfer()]`

- SrcDeps:
  - `ui.services.conflict_resolver`
  - `ui.dialogs.conflicts`
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Signal`
  - `PySide6.QtCore.Slot`
  - `PySide6.QtCore.QMimeData`
  - `PySide6.QtCore.QUrl`
  - `PySide6.QtGui.QClipboard`
  - `PySide6.QtGui.QGuiApplication`

API:
  - FileManager(QObject):
    - copy_selection() -> None: Sets clipboard for copy.
    - cut_selection() -> None: Sets clipboard for cut.
    - paste_to_current() -> None: Triggers paste in current tab.
    - trash_selection() -> None: Sends selected items to trash via TransactionManager.
    - rename_selection() -> None: Emits renameRequested signal on active tab's bridge.
    - create_new_folder() -> None: Creates "Untitled Folder" via file_ops with auto_rename.
    - duplicate_selection() -> None: Copies selected items to same folder with (Copy) suffix.
    - get_clipboard_files() -> List[str]: Reads paths from sys clipboard.
    - is_cut_mode() -> bool: Checks GNOME_COPIED_FILES mime for "cut" prefix.
    - get_cut_paths() -> List[str]: Returns cut paths or empty list.
    - handle_drop(urls, dest_dir, mode) -> None: Initiates transfer explicitly passing the drop intent.
!Caveat: `_run_transfer()` wraps `ConflictResolver` into a callback that maps `ConflictAction` enums to plain strings for the Core contract.

### [FILE: navigation_manager.py] [DONE]
Role: Maintains back/forward history stacks and tracks the current active path.

/DNA/: `[call:navigate(path) -> _back_stack.append(old) -> _forward_stack.clear() -> em:currentPathChanged]`

- SrcDeps:
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Signal`
  - `PySide6.QtCore.Slot`
  - `PySide6.QtCore.Property`

API:
  - NavigationManager(QObject):
    - navigate(path) -> None: Goes to path, updates history.
    - back() -> None: Navigates back.
    - forward() -> None: Navigates forward.

### [FILE: shell_manager.py] [DONE]
Role: Central QML coordinator initializing the main layout, sidebar sections (Quick Access/Volumes), and tab/navigation management.

/DNA/: `[init -> setup(QQuickView) -> addContextProperty(self)] + [bridge.itemsChanged -> call:_rebuild_sidebar_model() -> sidebar_model.update_section_items()] + [tab routing: add/close/next/prev -> TabListModel] + [nav routing: go_back/forward/home -> current_tab.go_*()]`

- SrcDeps:
  - `ui.models.tab_model.TabListModel`
  - `ui.models.tab_controller.TabController`
  - `ui.models.sidebar_model.SidebarModel`
  - `core.gio_bridge.desktop.QuickAccessBridge`
  - `core.gio_bridge.volumes.VolumesBridge`
- SysDeps:
  - `PySide6.QtWidgets.QWidget`
  - `PySide6.QtWidgets.QVBoxLayout`
  - `PySide6.QtCore.Qt`
  - `PySide6.QtCore.QUrl`
  - `PySide6.QtCore.Slot`
  - `PySide6.QtCore.Signal`
  - `PySide6.QtCore.Property`
  - `PySide6.QtCore.QTimer`
  - `PySide6.QtCore.QObject`
  - `PySide6.QtQuick.QQuickView`
  - `pathlib.Path`

API:
  - ShellManager(QWidget):
    - currentIndex [Property(int)]: Active tab index, notifies QML.
    - quickAccess [Property(QObject)]: Exposes QuickAccessBridge to QML.
    - volumes [Property(QObject)]: Exposes VolumesBridge to QML.
    - add_tab(path) -> TabController: Appends a new tab to model.
    - close_tab(index) -> None: Disposes tab and adjusts currentIndex.
    - next_tab() / prev_tab() -> None: Cycles active tab index.
    - close_current_tab() -> None: Closes the active tab.
    - navigate_to(path) -> None: Navigates active tab to path.
    - current_tab -> TabController: Returns the active TabController.
    - go_back() / go_forward() / go_home() -> None: Delegates to active tab's history.
    - _rebuild_sidebar_model() -> None: Pushes updated bridge data into existing `SidebarModel` instances.
!Caveat: `SidebarModel` contains hardcoded MOCK sections alongside dynamically populated sections for UI scroll testing.

### [FILE: view_manager.py] [DONE]
Role: Global controller for view adjustments (zoom level, toggling hidden files) that acts on the active tab.

/DNA/: `[call:zoom_in() -> tab.change_zoom() -> em:zoomChanged(height)]`

- SrcDeps:
- SysDeps:
  - `PySide6.QtCore.QObject`
  - `PySide6.QtCore.Slot`
  - `PySide6.QtCore.Signal`

API:
  - ViewManager(QObject):
    - zoom_in() -> None: Increases zoom.
    - zoom_out() -> None: Decreases zoom.
    - reset_zoom() -> None: Sets to default size.
    - select_all() -> None: Emits selectAllRequested on active tab.
    - toggle_hidden() -> None: Flips scanner state and forces rescan.
