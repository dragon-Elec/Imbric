# Backend Audit: Core Infrastructure Status

> **Executive Summary**: The `FileScanner` is robust and complete. However, the rest of the backend is missing critical "Manager" layers. To achieve the "API way for files with one job" goal, we need to refactor `FileOperations` into a Job-based system.

## 🟢 Ready (The "True Provider")

### `core/gio_bridge/scanner.py`
- **Status**: ✅ Complete
- **Capabilities**: 
  - Async Batched Enumeration (Non-blocking)
  - Rich Metadata (MIME, Permissions, timestamps, Symlinks)
  - **New**: Async Child Counting (`count_worker.py`)
- **Verdict**: Solid foundation. No changes needed immediately.

---

## 🟡 Needs Refactoring (The "One Job" Issue)

### `core/file_operations.py`
- **Current State**: "Fire and Forget" per file.
- **The Problem**: 
  - `trashMultiple([a, b, c])` → Triggers 3 separate threads/signals.
  - No concept of a "Single Transaction" (e.g., "Copying 50 files").
  - UI receives 50 separate start/finish events, making progress bars jittery.
- **Missing API**: `JobManager`.
  - Needs: `Job` class (UUID, total_files, current_file, progress 0-1.0).
  - Needs: `BackgroundJob` runner that queues these jobs.

### `core/gio_bridge/volumes.py`
- **Current State**: Lists *mounted* volumes only.
- **Missing**: 
  - Monitoring (auto-refresh on plug/unplug).
  - Mounting/Unmounting logic for unmounted drives.

---

## 🔴 Missing / Stubs (Feature Blockers)

These files exist but contain **NO logic** (`raise NotImplementedError`). Features depending on them **will not work**.

| Module | Status | Blocks |
|:-------|:-------|:-------|
| `core/undo_manager.py` | ❌ STUB | **Undo/Redo** (Ctrl+Z) |
| `core/search.py` | ❌ STUB | **File Search** (Ctrl+F) |
| `core/file_properties.py` | ❌ STUB | **Properties Dialog**, Detailed List View |
| `core/shortcuts.py` | ❌ STUB | **Custom Keybinds**, Centralized control |

## Recommended Roadmap

1.  **Refactor Props**: Implement `FileProperties` (Low hanging fruit, needed for details).
2.  **Refactor Ops**: Convert `FileOperations` to a **Job-based system** (Fixes "One Job" issue).
3.  **Implement Search**: Fill `search.py` stub.
4.  **Implement Undo**: Fill `undo_manager.py` stub (Requires Job system first).
