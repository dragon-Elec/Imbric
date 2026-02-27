Identity: Blocking modal UI dialogs for gathering explicit user input.

Rules:
- Must exclusively handle UI presentation logic (QDialog, QWidget).
- Never execute file I/O or VFS operations locally.
- Keep dialog data exchange simple (e.g., returning Enums or booleans).

Atomic Notes:
- `!Rule: [Dumb Dialogs] - Reason: Dialogs should only collect user intent during blocking operations (like Skip vs Overwrite) and return it, leaving execution fully up to calling managers.`

Index: None

---

### [FILE: conflicts.py] [DONE]
Role: Modal dialog to prompt users on file path collisions during transfer operations.

/DNA/: [instantiate:QDialog] -> wait:user_input -> em:Button.clicked -> call:_finish(Action) => {ConflictAction, apply_to_all}

- SrcDeps:
  - None
- SysDeps:
  - enum.Enum, auto
  - PySide6.QtWidgets.[QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame]
  - PySide6.QtCore.Qt
  - PySide6.QtGui.QIcon
  - gi.repository.Gio

API:
  - ConflictAction(Enum):
    - SKIP, OVERWRITE, RENAME, CANCEL
  - ConflictDialog(QDialog):
    - __init__(parent, src_path, dest_path): Sets up UI warning.
    - _finish(action: ConflictAction) -> None: Sets `self.action`, `self.apply_to_all`, and `accept()`s the dialog.
!Caveat: Does not return a value via exec(), caller must read `dialog.action` and `dialog.apply_to_all` after it closes.
