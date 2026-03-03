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
Role: Dynamically constructs and registers all global `QAction` objects from the `Shortcuts` model, mapping them to GNOME symbolic icons.

/DNA/: [loop: bindings.items() -> call:_create_action() -> setIcon(fromTheme:symbolic) -> setShortcut(model) -> connect(slot) -> window.addAction()]

- SrcDeps:
  - ui.models.shortcuts
- SysDeps:
  - PySide6.QtCore.QObject
  - PySide6.QtCore.Qt
  - PySide6.QtGui.QAction
  - PySide6.QtGui.QKeySequence
  - PySide6.QtGui.QIcon
  - PySide6.QtWidgets.QWidget

API:
  - ActionManager(QObject):
    - setup_actions(...) -> None: Binds all shortcuts to manager methods.
    - get_action(enum_id) -> Optional[QAction]: Retrieves a specific standard action.

### [FILE: file_manager.py] [DONE]
Role: Consolidates clipboard state, file action dispatch (trash, rename, duplicate), and drag/drop handling.

/DNA/: [action_slot() -> _get_selection() -> mw.transaction_manager/file_ops] + [_set_clipboard(paths, is_cut) -> create_desktop_mime_data -> em:clipboardChanged] + [handle_drop() -> batchTransfer(mode)] + [_run_transfer() -> ConflictResolver callback -> batchTransfer()]

- SrcDeps:
  - core.gio_bridge.desktop
  - core.metadata_utils
  - ui.services.conflict_resolver
  - ui.dialogs.conflicts
- SysDeps:
  - PySide6.QtCore.QObject
  - PySide6.QtCore.Signal
  - PySide6.QtCore.Slot
  - PySide6.QtCore.QMimeData
  - PySide6.QtCore.QUrl
  - PySide6.QtGui.QClipboard
  - PySide6.QtGui.QGuiApplication

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

/DNA/: [call:navigate(path) -> _back_stack.append(old) -> _forward_stack.clear() -> em:currentPathChanged]

- SrcDeps:
- SysDeps:
  - PySide6.QtCore.QObject
  - PySide6.QtCore.Signal
  - PySide6.QtCore.Slot
  - PySide6.QtCore.Property

API:
  - NavigationManager(QObject):
    - navigate(path) -> None: Goes to path, updates history.
    - back() -> None: Navigates back.
    - forward() -> None: Navigates forward.

### [FILE: shell_manager.py] [DONE]
Role: Central QML coordinator managing the unified shell (Sidebar + Tabs), injecting context-responsive ViewModels for Gtk-mimic menus.

/DNA/: [init -> setup(QQuickView) -> ctx.setContextProperty(shell|tab|sidebar|contextMenuViewModel)] + [bridges.em:changed -> call:_rebuild_sidebar_model -> sidebar_model.update] + [QML.em:navigationRequested -> call:navigate_to] + [tab routing: add/close/next/prev -> TabListModel]

- SrcDeps:
  - ui.models.tab_model.TabListModel
  - ui.models.tab_controller.TabController
  - ui.models.sidebar_model.SidebarModel
  - ui.models.context_menu_model.ContextMenuViewModel
  - core.gio_bridge.desktop.QuickAccessBridge
  - core.gio_bridge.volumes.VolumesBridge
  - core.image_providers.thumbnail_provider.ThumbnailProvider
  - core.image_providers.theme_provider.ThemeImageProvider
- SysDeps:
  - PySide6.QtQuick.QQuickView
  - PySide6.QtCore.QObject, Qt, QUrl, Slot, Signal, Property, QTimer
  - pathlib.Path

API:
  - ShellManager(QObject):
    - currentIndex [Property(int)]: Active tab index with QML notification.
    - quickAccess [Property(QObject)]: Exposes QuickAccessBridge.
    - volumes [Property(QObject)]: Exposes VolumesBridge.
    - add_tab(path) -> TabController: Appends tab to model and sets currentIndex to new tab.
    - close_tab(index) -> None: Removes tab from model and resets currentIndex if out of bounds.
    - next_tab() / prev_tab() -> None: Cycles active tab index with wrap-around.
    - close_current_tab() -> None: Closes active tab.
    - navigate_to(path) -> None: Navigates active tab to path.
    - current_tab -> TabController: Returns active TabController instance.
    - go_back() / go_forward() / go_home() -> None: Delegates history navigation to active tab.
    - _rebuild_sidebar_model() -> None: Syncs bridge data to SidebarModel.
    - _on_section_toggled(title, collapsed) -> None: Persists sidebar section collapse state.
!Caveat: Decoupled from `QWidget` inheritance; use `container` property for embedding in `QMainWindow`.

### [FILE: view_manager.py] [DONE]
Role: Global controller for view adjustments (zoom level, toggling hidden files) that acts on the active tab.

/DNA/: [call:zoom_in() -> tab.change_zoom() -> em:zoomChanged(height)]

- SrcDeps:
- SysDeps:
  - PySide6.QtCore.QObject
  - PySide6.QtCore.Slot
  - PySide6.QtCore.Signal

API:
  - ViewManager(QObject):
    - zoom_in() -> None: Increases zoom.
    - zoom_out() -> None: Decreases zoom.
    - reset_zoom() -> None: Sets to default size.
    - select_all() -> None: Emits selectAllRequested on active tab.
    - toggle_hidden() -> None: Flips scanner state and forces rescan.
