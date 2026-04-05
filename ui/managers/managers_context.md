Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/ui/managers
Routing layer for high-level UI coordination. Managers sit above the bridges and models to provide application-wide state (clipboard, navigation stacks, shell structure) and coordinate operations across tabs and core services.

Rules:
- Managers must be initialized in `MainWindow.__init__` and cross-connected if needed.
- Heavy logic should be deferred to the `core` package or background workers.
- Avoid circular dependencies between managers (e.g., ShellManager <=> FileManager).

Atomic Notes:
!Decision: [ShellManager > TabManager] - Reason: ShellManager was renamed to reflect its broader role in managing the unified QML shell (sidebar + tabs) rather than just tab lifecycle.
!Pattern: [Delegation to Active Tab] - Reason: ActionManager and ViewManager delegate all operations to `shell_manager.current_pane` to ensure consistent context-sensitive behavior.

Index: None

---

### [FILE: action_manager.py] [USABLE]
Role: Dynamically constructs and registers all global QAction objects from the Shortcuts model, mapping them to GNOME symbolic icons.

/DNA/: [loop: bindings.items() -> call:_create_action() -> setIcon(fromTheme:symbolic) -> setShortcut(model) -> connect(slot) -> window.addAction()]

- SrcDeps: .models.shortcuts
- SysDeps: PySide6{QtCore, QtGui, QtWidgets}, typing

API:
  - ActionManager(QObject):
    - setup_actions(window, shortcuts, file_manager, view_manager, shell_manager, undo_manager) -> void: Binds all shortcuts to manager methods and adds actions to window.
    - get_action(enum_id: ShortcutAction) -> QAction | None: Retrieves a specific standard action.
    - get_icon(action_name: str) -> str: [Slot] Returns the symbolic icon name for a given action string for QML.

### [FILE: file_manager.py] [USABLE]
Role: Consolidates clipboard state, file action dispatch (trash, rename, duplicate), and drag/drop handling.

/DNA/: [action_slot() -> _get_selection() -> mw.transaction_manager/file_ops] + [_set_clipboard(paths, is_cut) -> create_desktop_mime_data -> em:clipboardChanged] + [handle_drop() -> batchTransfer(mode)] + [_run_transfer() -> ConflictResolver callback -> batchTransfer()]

- SrcDeps: .services.conflict_resolver, .dialogs.conflicts, core.backends.gio.{desktop, helpers}, core.utils.path_ops
- SysDeps: PySide6.QtCore{QObject, Signal, Slot, QMimeData, QUrl}, PySide6.QtGui{QClipboard, QGuiApplication}, typing

API:
  - FileManager(QObject):
    - copy_selection() -> void: Sets clipboard for copy. [Slot]
    - cut_selection() -> void: Sets clipboard for cut. [Slot]
    - paste_to_current() -> void: Triggers paste in the active tab's folder. [Slot]
    - trash_selection() -> void: Sends selected items to trash via TransactionManager. [Slot]
    - rename_selection() -> void: Emits renameRequested signal on active tab's bridge. [Slot]
    - create_new_folder() -> void: Creates "Untitled Folder" via file_ops with auto_rename. [Slot]
    - duplicate_selection() -> void: Copies selected items to same folder with (Copy) suffix. [Slot]
    - get_clipboard_files() -> list: Reads paths from system clipboard.
    - is_cut_mode() -> bool: Checks GNOME_COPIED_FILES mime for "cut" prefix.
    - get_cut_paths() -> list: Returns cut paths or empty list.
    - handle_drop(urls: list, dest_dir: str|None, mode: str) -> void: Initiates transfer explicitly passing the drop intent. [Slot]
!Caveat: _run_transfer() wraps ConflictResolver into a callback that maps ConflictAction enums to plain strings for the Core contract.

### [FILE: navigation_manager.py] [USABLE]
Role: Maintains back/forward history stacks and tracks the current active path.

/DNA/: [call:navigate(path) -> _back_stack.append(old) -> _forward_stack.clear() -> em:currentPathChanged]

- SrcDeps: None
- SysDeps: PySide6.QtCore{QObject, Signal, Slot, Property}

API:
  - NavigationManager(QObject):
    - navigate(path) -> void: Goes to path, updates history.
    - back() -> void: Navigates back.
    - forward() -> void: Navigates forward.
    - currentPath() -> str: [Property] Returns the current active path.
    - canGoBack() -> bool: [Property] True if back stack is not empty.
    - canGoForward() -> bool: [Property] True if forward stack is not empty.

### [FILE: shell_manager.py] [USABLE]
Role: Central QML coordinator managing the unified shell (Sidebar + Panes), injecting context-responsive ViewModels for Gtk-mimic menus.

/DNA/: [init -> setup(QQuickView) -> ctx.setContextProperty(shellManager|tabModel|sidebarModel|contextMenuViewModel)] + [bridges.em:changed -> call:_rebuild_sidebar_model -> sidebar_model.update] + [QML.em:navigationRequested -> call:navigate_to] + [pane routing: add/close/next/prev -> TabListModel]

- SrcDeps: .models.{tab_model, pane_context, sidebar_model, context_menu_model}, core.backends.gio.desktop.QuickAccessBridge, core.backends.gnome_thumbnailer.{provider, theme_icons}
- SysDeps: PySide6{QtQuick, QtCore, QtWidgets}, pathlib.Path

API:
  - ShellManager(QObject):
    - currentIndex() -> int: [Property] Active tab index with QML notification.
    - quickAccess() -> QObject: [Property] Exposes QuickAccessBridge.
    - volumes() -> QObject: [Property] Exposes VolumesBridge.
    - current_pane() -> PaneContext: [Property] Returns the active logical engine instance.
    - add_tab(path: str|None) -> PaneContext: Appends tab to model and sets currentIndex to new tab.
    - close_tab(index: int) -> void: Removes tab from model and resets currentIndex if out of bounds.
    - next_tab() / prev_tab() -> void: Cycles active Pane Context index with wrap-around.
    - close_current_tab() -> void: Closes active tab and its associated engine.
    - navigate_to(path: str) -> void: Navigates the active Pane Context to path.
    - go_back() / go_forward() / go_home() / go_up() -> void: Delegates history navigation to the active Pane Context.
    - _rebuild_sidebar_model() -> void: Syncs bridge data to SidebarModel.
    - _on_section_toggled(title, collapsed) -> void: Persists sidebar section collapse state.
!Caveat: Decoupled from QWidget inheritance; use container property for embedding in QMainWindow.

### [FILE: view_manager.py] [USABLE]
Role: Global controller for view adjustments (zoom level, toggling hidden files) that acts on the active Pane Context.

/DNA/: [call:zoom_in() -> tab.change_zoom() -> em:zoomChanged(height)]

- SrcDeps: None
- SysDeps: PySide6.QtCore{QObject, Slot, Signal}

API:
  - ViewManager(QObject):
    - zoom_in() -> void: Increases zoom. [Slot]
    - zoom_out() -> void: Decreases zoom. [Slot]
    - reset_zoom() -> void: Sets to default size. [Slot]
    - select_all() -> void: Emits selectAllRequested on active tab. [Slot]
    - toggle_hidden() -> void: Flips scanner state and forces rescan. [Slot]
