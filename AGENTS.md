# Agent Instructions for Imbric

This document provides essential information for agentic coding agents operating in the Imbric repository. Imbric is a photo-first file manager for GNOME, built with PySide6 and utilizing GIO for low-level filesystem operations.

## 🛠 Build, Lint, and Test Commands

### Environment Setup
- **Python Version:** 3.10 or higher.
- **System Dependencies:** `python3-gi`, `gir1.2-gnomedesktop-3.0` (required for GIO/GnomeDesktop integration).
- **Python Dependencies:** `PySide6`, `psutil`.

### Core Commands
- **Run Application:** `python main.py [path]`
- **Linting:** `flake8 .` (Configured in `.flake8`, max-line-length is 127).
- **Testing:** `pytest`
- **Run Single Test File:** `pytest tests/test_metadata_utils.py`
- **Run Specific Test:** `pytest tests/test_metadata_utils.py::test_format_size`

---

## 🎨 Code Style Guidelines

### 1. Imports & GIO Integration
- **Order:** Standard library, PySide6/Third-party, Project-specific imports.
- **GIO Safety:** ALWAYS call `gi.require_version` before importing from `gi.repository`.
  ```python
  import gi
  gi.require_version('Gio', '2.0')
  from gi.repository import Gio, GLib
  ```
- **Project Imports:** Use absolute-style imports from the root (e.g., `from core.file_operations import FileOperations`).

### 2. Naming Conventions
- **Classes:** `PascalCase` (e.g., `FileOperations`, `MainWindow`).
- **Methods/Functions:** A hybrid approach is used:
    - **Qt Signals/Slots/Public API:** Often `camelCase` to match Qt conventions (e.g., `operationStarted`, `setUndoManager`).
    - **Internal/Logic Methods:** `snake_case` (e.g., `_on_started`, `scan_directory`).
- **Variables:** `snake_case`.

### 3. Typing & Documentation
- **Type Hints:** Required for all public methods and recommended for internal ones.
  ```python
  def move(self, source_path: str, dest_path: str, overwrite: bool = False) -> str:
  ```
- **Docstrings:** Use Google-style or concise descriptive docstrings for classes and complex methods.

### 4. Error Handling
- **GIO/GLib Errors:** Wrap low-level GIO calls in `try...except GLib.Error`.
- **Signals:** Use signals to propagate errors from background workers to the UI (e.g., `operationError.emit(...)`).

### 5. Architectural Patterns
- **Non-blocking I/O:** Never perform heavy I/O on the main thread. Use `QThreadPool` with `QRunnable` or GIO's async API (`enumerate_children_async`).
- **State Management:** The `TransactionManager` is the single source of truth for file operations. All modifications should ideally go through it to support Undo/Redo.
- **UI:** The application uses a mix of PySide6 Widgets for the shell and QML for the masonry file view.

### 6. Formatting
- **Indentation:** 4 spaces.
- **Line Length:** Up to 127 characters as defined in `.flake8`.
