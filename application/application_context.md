Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/application
Application UI entry point. Coordinates the main window lifecycle, global service wiring, and assembly of widgets into the primary shell.

Rules:
- UI components must be initialized in `_setup_ui()` and wired to managers in `__init__`.
- Global signals (navigation, progress) must be routed through `MainWindow` or `ShellManager` to ensure cross-tab consistency.

Atomic Notes:
!Decision: [ShellManager > Direct QML] - Reason: MainWindow delegates all QML tab/sidebar management to ShellManager to keep the window class focused on wiring.

Index:
- bridges: Python-to-QML data bridges for views.
- dialogs: Modal interaction windows.
- managers: Application-wide state and coordination logic.
- models: Data structures and view models.
- qml: Declarative UI components and view layouts.
- services: Heavy-lifting UI logic (search, conflict resolution).
- styles: QSS and visual theme definitions.
- widgets: Reusable Python-based UI components (NavigationBar, StatusBar).

---

### [FILE: main_window.py] [USABLE]
Role: Primary application window assembling the unified shell, navigation entry, and core service coordination.

/DNA/: [init:core_logic] -> [setup:shell_manager] -> [assemble:shell_container + status_bar + overlay] -> [connect:shell.currentPathChanged -> _on_tab_path_changed -> watch:path + sync:status_bar]

- SrcDeps: .managers.{shell_manager, action_manager, file_manager, view_manager}, .widgets.{status_bar, progress_overlay}, .models.shortcuts, core.registry, core.managers.{FileOperations, TransactionManager, UndoManager}, core.backends.gio.{monitor, volumes, metadata_workers, backend}, core.services.validator
- SysDeps: PySide6{QtWidgets, QtCore}, gi.repository.Gio, pathlib, os

API:
  - MainWindow(QMainWindow):
    - navigate_to(path) -> void: Primary entry point for changing the active view path.
    - go_up() -> void: Delegates to `shell_manager` for parent path navigation.
    - change_zoom(delta) -> void: Forwards legacy zoom requests to `ViewManager`.
    - closeEvent(event) -> void: Triggers `file_ops.shutdown()` before exiting.
    - _on_tab_path_changed(path) -> void: Syncs FileMonitor and StatusBar when active tab or path changes.
    - bridge -> object: [Property] Returns bridge of the current active pane.
    - current_path -> str: [Property] Returns path of the current active pane.
    - qml_view -> QQuickWidget: [Property] Returns the shell's shared QML view.
!Caveat: `_on_directory_changed` is a no-op to prevent global reloads in favor of surgical updates.
