Identity: Reusable, self-contained Python-based UI components bridging Qt Widgets into the Imbric architecture.

Rules:
- Widgets must be decoupled; emit Signals for actions rather than calling core managers directly.
- Visual state updates should be driven by Slots receiving data from Models/Controllers, not by parsing the filesystem natively.
- Avoid placing blocking or heavy business logic inside widget classes.

Atomic Notes:
!Pattern: [Dumb Widgets] - Reason: NavigationBar only emits requests (e.g. navigateRequested) and lets handlers coordinate traversal.
!Pattern: [Layout Injection] - Reason: NavigationBar is initialized by MainWindow and injected into either CustomHeader (CSD) or the central layout (Standard).
!Rule: [Non-blocking UX] - Reason: Long-running operations use ProgressOverlay instead of modal dialogs to prevent locking the UI thread.

Index: None

---

### [FILE: custom_header.py] [USABLE]
Role: Experimental CSD title bar that wraps NavigationBar and provides min/max/close controls.

/DNA/: `[receive:nav_bar -> layout.add(nav_bar) + layout.add(controls)] + [em:mousePress -> win.startSystemMove()] + [em:doubleClick -> win.toggleMaximize()]`

- SrcDeps: None (Takes NavigationBar as injected dependency)
- SysDeps: PySide6{QtWidgets, QtGui, QtCore}

API:
  - CustomHeader(QWidget):
    - __init__(navigation_bar, parent=None): Embeds nav bar and window controls.
!Caveat: Assumes the parent window has the `Qt.FramelessWindowHint` flag set.

---
 
### [FILE: drag_helper.py] [USABLE]
Role: Lightweight wrapper for initiating system-native drag-and-drop sessions using centralized MIME logic.

/DNA/: `[call:start_drag_session(paths) -> create_desktop_mime_data -> drag.setMimeData -> drag.exec(MoveAction)]`

- SrcDeps: core.backends.gio.{helpers, desktop}
- SysDeps: PySide6{QtCore, QtGui}

API:
  - start_drag_session(mainwindow, paths) -> None: Initiates a system drag using the appropriate source widget.
 
---
 
### [FILE: navigation_bar.py] [USABLE]
Role: Primary navigation controls: up/back, address bar, and zoom modifiers.

/DNA/: `[wait:user_input] -> em:navigateRequested(path) | em:zoomChanged(delta) | em:upRequested`

- SrcDeps: None
- SysDeps: PySide6{QtWidgets, QtGui, QtCore}

API:
  - NavigationBar(QWidget):
    - navigateRequested(str) / zoomChanged(int) / upRequested() [Signals].
    - set_path(path) -> None: Updates visible path bar silently.
    - focus_path() -> None: Focuses and selects all text.
    - showError(msg) -> None: Temporary error state for address bar.

---

### [FILE: progress_overlay.py] [USABLE]
Role: Non-blocking slide-up progress indicator for file operations and transactions.

/DNA/: `[em:OperationStarted -> start:show_timer -> _do_show] + [em:Progress -> update:QProgressBar] + [em:Completed -> _do_hide]`

- SrcDeps: None
- SysDeps: PySide6{QtWidgets, QtCore, QtGui}

API:
  - ProgressOverlay(QFrame):
    - cancelRequested(job_id) [Signal].
    - onOperationStarted, onOperationProgress, onOperationCompleted [Slots].
    - onBatchStarted, onBatchProgress, onBatchFinished [Slots].
    - onOperationError, onBatchUpdate [Slots].
!Caveat: Implements a deliberate 300ms delayed show to prevent flickering.

---

### [FILE: status_bar.py] [USABLE]
Role: Bottom status bar displaying directory item counts and active selection info.

/DNA/: `[em:updateItemCount -> ++:total_items -> _show_idle_status] + [em:updateSelection -> show:count | revert:idle]`

- SrcDeps: None
- SysDeps: PySide6{QtWidgets, QtCore}

API:
  - StatusBar(QStatusBar):
    - updateItemCount(session, files) [Slot]: Accumulates batch counts.
    - resetCounts() [Slot]: Resets counters for new folder load.
    - updateSelection(paths) [Slot]: Shows selection count.
    - setMessage(msg) / updateAttribute(path, attr, val) [Slots].
