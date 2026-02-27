Identity: Reusable, self-contained Python-based UI components bridging Qt Widgets into the Imbric architecture.

Rules:
- Widgets must be decoupled; emit Signals for actions rather than calling core managers directly.
- Visual state updates should be driven by Slots receiving data from Models/Controllers, not by parsing the filesystem natively.
- Avoid placing blocking or heavy business logic inside widget classes.

Atomic Notes:
- `!Pattern: [Dumb Widgets] - Reason: Widgets like NavigationBar only emit requests (e.g. navigateRequested) and let the TabController handle the actual traversal and history.`
- `!Rule: [Non-blocking UX] - Reason: Long-running operations use ProgressOverlay instead of modal dialogs to prevent locking the main UI thread during background copies.`

Index: None

---

### [FILE: custom_header.py] [DONE]
Role: Experimental Client-Side Decoration (CSD) header providing custom window controls and dragging.

/DNA/: [instantiate] -> wrap(NavigationBar) + wrap(WindowControls) -> [em:mousePress] -> call:windowHandle.startSystemMove()

- SrcDeps:
  - None (Takes NavigationBar as injected dependency)
- SysDeps:
  - PySide6.QtWidgets.[QWidget, QHBoxLayout, QToolButton, QSizePolicy, QApplication]
  - PySide6.QtGui.QIcon
  - PySide6.QtCore.Qt

API:
  - CustomHeader(QWidget):
    - __init__(navigation_bar, parent=None): Embeds nav bar and creates min/max/close buttons.
!Caveat: Assumes the parent window has the `Qt.FramelessWindowHint` flag set.

---

### [FILE: navigation_bar.py] [DONE]
Role: Unified navigation controls including Up button, Path entry, and Zoom controls.

/DNA/: [wait:user_input] -> em:navigateRequested(path) | em:zoomChanged(delta)

- SrcDeps:
  - None
- SysDeps:
  - PySide6.QtWidgets.[QWidget, QHBoxLayout, QToolButton, QLineEdit, QSizePolicy, QToolTip]
  - PySide6.QtGui.[QIcon, QKeySequence, QAction]
  - PySide6.QtCore.[Qt, Slot, Signal, QTimer]
  - gi.repository.Gio

API:
  - NavigationBar(QWidget):
    - navigateRequested(str) [Signal]: Emitted when path is submitted or Up is clicked.
    - zoomChanged(int) [Signal]: Emitted with +1 or -1 delta.
    - set_path(path: str) -> None: Silently updates the visible path without emitting signals.
    - showError(error_msg: str) -> None: Temporarily shows a red error border and tooltip.

---

### [FILE: progress_overlay.py] [DONE]
Role: Non-blocking, nautilus-style slide-up overlay for file operation progress.

/DNA/: [em:OperationStarted] -> start:delay_timer -> [show:overlay] -> [em:Progress] -> update:QProgressBar -> [em:Completed] -> hide:overlay

- SrcDeps:
  - None
- SysDeps:
  - PySide6.QtWidgets.[QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QPushButton, QFrame]
  - PySide6.QtCore.[Qt, QTimer, Signal, Slot, QPropertyAnimation, QEasingCurve]
  - PySide6.QtGui.QIcon

API:
  - ProgressOverlay(QFrame):
    - cancelRequested(str) [Signal]: Emitted with job_id when user clicks cancel.
    - onOperationStarted(job_id, op_type, path) [Slot]: Stages UI, waits 300ms before showing.
    - onOperationProgress(job_id, current, total) [Slot]: Updates progress bar and MB counters.
    - onOperationCompleted(op_type, path, result_data) [Slot]: Auto-hides or stays open if partial failure detected.
    - onBatchStarted, onBatchProgress, onBatchFinished [Slots]: Transaction manager equivalents.
!Caveat: Implements a deliberate 300ms delayed show to prevent flickering on operations that complete almost instantly.

---

### [FILE: status_bar.py] [DONE]
Role: Bottom status bar displaying selected item counts and folder composition.

/DNA/: [em:filesFound] -> ++:accumulated_counts -> call:_show_idle_status() -> update:status_label

- SrcDeps:
  - None
- SysDeps:
  - PySide6.QtWidgets.[QStatusBar, QLabel]
  - PySide6.QtCore.Slot

API:
  - StatusBar(QStatusBar):
    - updateItemCount(session_id, files) [Slot]: Accumulates incoming batch counts (folders vs files).
    - resetCounts() [Slot]: Clears counters before a fresh directory scan.
    - updateSelection(selected_paths) [Slot]: Swaps display to "X items selected" when active.
