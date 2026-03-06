Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/ui
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

### [FILE: main_window.py] [DONE]
Role: Primary application window assembling the unified shell, navigation entry, and core service coordination.

/DNA/: [init:core_logic] -> [setup:shell_manager] -> [assemble:nav_bar + status_bar + overlay] -> [connect:nav_bar.navigateRequested -> navigate_to] -> [on_tab_changed -> sync:nav_bar + watch:path]

- SrcDeps: .managers.shell_manager, .widgets.{navigation_bar, status_bar, progress_overlay}, core.{file_operations, transaction_manager, file_monitor}
- SysDeps: PySide6{QtWidgets, QtCore}, gi.repository.Gio

API:
  - MainWindow(QMainWindow):
    - navigate_to(path) -> void: Primary entry point for changing the active view path.
    - go_up() -> void: Calculates parent path via Gio and triggers navigation.
    - _on_tab_path_changed(path) -> void: Syncs NavigationBar and FileMonitor when user swaps tabs.
