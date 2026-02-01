# Imbric: Architecture & Safety Reference

> **MAINTENANCE GUIDE:** Optimize for **LLM token efficiency + human readability**.
>
> **Token-Efficient Patterns:**
> - **Bullet lists** > tables (pipes/alignment waste tokens)
> - **Fragment sentences** > prose ("Async enum via Gio" not "This module is used for...")
> - **Common words** tokenize better than rare jargon
> - **Inline code** for identifiers: `copy()`, `Gio.File`
> - **Consistent abbreviations:** MED, LOW, [TODO], [NEW]
>
> **When to Use Tables:** Only for 3+ columns or structured comparison.
>
> **Update Rules:** Session notes → Section 8 only. No changelog prose.

> **Version:** 0.7.4-alpha | **Updated:** 2026-01-31 | **Status:** Active  
> **Target:** Linux (GNOME) | **Stack:** Python 3.10+ / PySide6 / QML / Gio / GnomeDesktop

---

## Quick Context (Fresh Session Start Here)

**What:** Photo-first file manager with Masonry layout, native GNOME integration.

**Current Phase:** Phase 5 (Async I/O) — Non-blocking file ops with progress overlay.

**Critical Patterns:**
- **"Lens, not Engine":** Defer I/O to `Gio`, thumbnails to `GnomeDesktop`
- **Masonry:** "Card Dealing" round-robin into N columns (not position math)
- **Input:** Hybrid — per-delegate `TapHandler`/`DragHandler` + global `MouseArea` for marquee selection
- **Menus:** Hybrid — QML emits signal → Python shows native `QMenu`

**Dependencies:** `PySide6`, `PyGObject`, `gir1.2-gnomedesktop-3.0`

---

## Development Approach: Stub-First / API-First

> **What is a Stub?** A stub file contains the **complete structure** (classes, functions, docstrings, type hints) but **no implementation** (just `pass` or `raise NotImplementedError`). The API is defined, the "contract" is clear, but the logic is empty.

**Why We Use This:**
- **See all the pieces** — Every helper file exists in the codebase, even if not implemented yet
- **One thing at a time** — Implement one file, test it thoroughly, mark as done, move on
- **Self-documenting** — Docstrings explain what each function should do
- **No surprises** — The interface is stable before implementation
- **Isolation** — Each file does one thing and does it well

**File Status Markers:**
- `[STUB]` — Structure defined, no implementation (raises `NotImplementedError`)
- `[WIP]` — Implementation in progress, not fully tested
- `[DONE]` — Implemented, tested — don't touch unless broken

**Stub File Convention:**
- Each stub has a docstring header: `"""[STUB] Description..."""`
- All public methods raise `NotImplementedError("TODO: Implement")`
- When fully implemented and tested, change to `"""[DONE] Description..."""`

---

## Table of Contents

1. [File Reference (All Modules)](#1-file-reference)
2. [Architecture Overview](#2-architecture-overview)
3. [Safety Mechanisms](#3-safety-mechanisms)
4. [Data Flows](#4-data-flows)
5. [Historical Decisions](#5-historical-decisions)
6. [AI Session Notes](#6-ai-session-notes)

---

## 1. File Reference

### 1.1. Core Layer (`core/`)

#### `core/metadata_utils.py` — File Metadata Logic `[NEW]`
Unified utility for Gio metadata extraction. Single source of truth for:
- `get_file_info(path)` → `FileInfo` dataclass
- `format_size(bytes)`
- `resolve_mime_icon(gfile)`
Used by `FileOperations`, `TrashManager`, and `FilePropertiesModel`.

#### `core/file_operations.py` — Operations Controller `[REFACTORED]`
Unified controller for all I/O (Standard + Trash). Orchestrates workers via `QThreadPool`.

- **Role:** Single source of truth for UI. Manages `jobs` dict and signals.
- **Methods:**
  - `copy()`, `move()`, `rename()`, `createFolder()`
  - `trash()`, `restore()`, `listTrash()`, `emptyTrash()`
  - `cancel(job_id)`
  - `setUndoManager(mgr)` — dependency injection
- **Signals:** Unified `operationStarted`, `operationProgress`, `operationFinished`, `operationError`.

#### `core/file_workers.py` — Standard Ops Logic `[DONE]`
Contains the `QRunnable` implementations for standard file operations.
- **Race Condition Safety:** Uses Atomic Retry Loops for `CreateFolder` and `Transfer` (auto-rename).
- `FileJob` (dataclass): Shared state (UUID, status, paths, auto-rename).
- `CopyRunnable`: Atomic rename loop + recursive copy.
- `MoveRunnable`: Move with "Directory Merge" logic and cross-device fallbacks.
- `RenameRunnable`: Wraps `Gio.set_display_name`.
- `CreateFolderRunnable`: Atomic retry loop for unique folder creation.

#### `core/trash_workers.py` — Trash Ops Logic `[NEW]`
Contains the `QRunnable` implementations for Trash operations.
- `SendToTrashRunnable`: Wraps `Gio.trash`.
- `RestoreFromTrashRunnable`: Restores via `trash://` URI, handles rename-on-restore.
- `ListTrashRunnable`: Enumerates `trash://` and builds `TrashItem` list.
- `EmptyTrashRunnable`: Recursively deletes `trash://` contents.
- `TrashItem` (dataclass): Metadata wrapper.

---

#### `core/gio_bridge/scanner.py` — Async Directory Enum
True async file listing via `Gio.enumerate_children_async`. Batches of 50.

- `FileScanner`:
  - `scan_directory(path)` — starts async scan
  - `_fetch_next_batch()` — recursive batch fetch
  - `_on_files_retrieved()` — filters hidden, reads image dimensions via `QImageReader`
- **Signals:** `filesFound(list[dict])`, `scanFinished()`, `scanError(str)`

---

#### `core/gio_bridge/bookmarks.py` — GTK Bookmarks
Parses `~/.config/gtk-3.0/bookmarks`.

- `BookmarksBridge.get_bookmarks()` → `[{name, path, icon}]`

---

#### `core/gio_bridge/count_worker.py` — Recursive Item Counter [NEW]
Background worker using `QThreadPool` + `os.scandir` for non-blocking directory size calc.

- `ItemCountWorker`:
  - `enqueue(path)` — adds folder to count queue
  - `countReady(path, count)` — signal emitted on completion
- Uses `C`-optimized `os.scandir` for speed over `pathlib`.

---

#### `core/gio_bridge/volumes.py` — Mounted Volumes
Wraps `Gio.VolumeMonitor`.

- `VolumesBridge.get_volumes()` → `[{name, path, icon, type}]`

---

#### `core/image_providers/thumbnail_provider.py` — Thumbnails
`QQuickImageProvider` using GNOME shared cache.

- `ThumbnailProvider.requestImage(id_path, size, requestedSize)`:
  - Check `~/.cache/thumbnails/` via `GnomeDesktop.DesktopThumbnailFactory`
  - Generate if missing
  - **Fallbacks:** Folder icon → MimeType icon → Original image (slow)
- `_get_themed_icon()` — helper for system icons

---





#### `core/file_monitor.py` — Directory Watcher
`Gio.FileMonitor` wrapper for live directory changes.

- `watch(path)` — start monitoring
- `stop()` — cancel monitoring
- **Signals:** `fileCreated`, `fileDeleted`, `fileChanged`, `fileRenamed`, `directoryChanged`

---

#### `core/undo_manager.py` — Undo/Redo Stack `[DONE]`
Tracks file operations with robust asynchronous job tracking.
- **Sync/Async Logic:** Captures `job_id`s from `FileOperations` and waits for `finished` signals before committing state.
- `undo()` / `redo()` — Entry points (pops tx, sets pending state).
- `setFileOperations()` — Signal wiring for completion tracking.
- `operationFinished` signal — Reports final outcome for UI feedback.
- **Note:** Prevents desync by validating filesystem outcome before rotating stacks.

---

#### `core/diagnostics.py` — Memory Profiling `[DONE]`
Internal debugging tool for tracking memory usage and object leaks.
- `MemoryProfiler`: Static utility class.
- `start()`: Enables `tracemalloc`.
- `print_report()`: Forces GC and prints object counts (focused on Imbric classes).
---

#### `core/sorter.py` — File Sorting `[DONE]`
Sorts file lists by name, date, size, or type.

- `sort(files, key, ascending)` → sorted list
- `setKey(SortKey)` / `setAscending(bool)`
- `SortKey` enum: `NAME`, `DATE_MODIFIED`, `SIZE`, `TYPE`

---

#### `core/transaction.py` — Transaction Data Models
Data definitions for batch operations.

- `Transaction` (dataclass): Batch wrapper with ID, description, status.
- `TransactionOperation` (dataclass): Atomic op definition (copy/move/trash).
- `TransactionStatus` (Enum): `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`.

---

#### `core/transaction_manager.py` — I/O Orchestrator `[DONE]`
Central nervous system for batch operations and conflict handling.

- `startTransaction(description)` — begins a new batch
- `addOperation(tid, op_type, src, dest)` — registers intent
- `resolveConflict(job_id, resolution, new_name)` — handles pause/resume logic
- **Signals:** `transactionStarted`, `transactionFinished`, `transactionProgress`, `conflictDetected`, `conflictResolved`

---

#### `core/search.py` — File Search `[DONE]`
Unified search engine with multiple backends.
- `FdSearchEngine`: Fast discovery via `fd` subprocess.
- `ScandirSearchEngine`: Pure Python `os.scandir` fallback.
- `get_search_engine()`: Auto-detection factory.

#### `core/search_worker.py` — Background Search Worker `[DONE]`
`QThread` implementation for non-blocking search.
- Batched results (50 items) for UI responsiveness.
- Supports runtime cancellation.

---



### 1.2. UI Managers (`ui/managers/`) [NEW]

#### `ui/managers/action_manager.py` — Actions & Shortcuts `[DONE]`
Central Action registry.
- `setup_actions()` — registers QActions with global shortcuts
- `get_action(name)` — retrieval for context menus

#### `ui/managers/navigation_manager.py` — History & Paths `[NEW]`
Manages navigation state (Back/Forward history).
- `navigate(path)`, `back()`, `forward()`.
- Tracks `canGoBack` / `canGoForward` states.

#### `ui/managers/file_manager.py` — File Ops Coordinator `[DONE]`
High-level orchestration of clipboard and complex operations.
- `copy_selection()`, `trash_selection()`, `handle_drop()`.
- Interface for `TransactionManager`.

#### `ui/managers/view_manager.py` — Layout & Selection `[DONE]`
Orchestrates Zoom, `select_all`, and Tab-specific visual state.
- Delegates to `ColumnSplitter` (Layout) and `SelectionHelper` (Marquee).

---

### 1.3. UI Models (`ui/models/`)

#### `ui/models/app_bridge.py` — QML Bridge (Simplified)
Simplified QML interface. Delegates heavy logic to Managers.

- `cutPaths` (Property)
- `startDrag(paths)`
- `showContextMenu(paths)` & `showBackgroundContextMenu()`
- `renameFile(old, new)`
- `startSearch()`, `cancelSearch`
- `selectPath(path)` — select file (post-operation)
- **Properties:** `targetCellWidth`

---

#### `ui/models/sidebar_model.py` — Sidebar Data
Combines bookmarks + volumes for sidebar QTreeView.

- `SidebarModel`: merges `BookmarksBridge` + `VolumesBridge`
- `refresh()` — reloads from both sources
- Roles: `name`, `path`, `icon`, `type`

---

### 1.4. UI Dialogs (`ui/dialogs/`) [NEW]

#### `ui/dialogs/conflicts.py` — Conflict Resolution
Moved from `elements`. Contains `ConflictDialog` and `ConflictResolver`.
- `resolve(src, dest)` → Copy mode `(Copy)`, `(Copy 2)`
- `resolve_rename(old, new)` → Rename mode `(2)`, `(3)`

#### `ui/dialogs/properties.py` — File Properties [NEW]
Replaces `FilePropertiesModel`.
- `PropertiesLogic.get_properties(path)` — fetches metadata

---

### 1.5. UI Components (`ui/components/`)
Renamed from `ui/elements`.

#### `ui/components/tab_manager.py` — Multi-Tab Browser
Wraps `QTabWidget`. Each tab owns its own `ViewManager` components.

#### `ui/components/navigation_bar.py` — Toolbar
#### `ui/components/sidebar.py` — Sidebar Widget
#### `ui/components/status_bar.py` — Status Feedback
Shows item counts (folders/files) and selection info.
- `updateAttribute(path, attr, value)` — Handles async scanner updates (child counts).
- `setMessage(str)` — Temporary status feedback.
#### `ui/components/progress_overlay.py` — Op Progress

---

### 1.6. UI Main (`ui/`)

#### `ui/main_window.py` — Application Shell
Orchestrator. Initializes Managers and Components.
- `setup_ui()` — builds structure
- `ActionManager.setup_actions()` — registers shortcuts
- Delegated logic: Zoom -> ViewManager, Ops -> FileManager

---

### 1.7. QML (`ui/qml/`)

#### `ui/qml/views/MasonryView.qml` — GPU Grid
Main photo grid with N `ListView` columns.

- **Input Model:** Hybrid — per-delegate `TapHandler`/`DragHandler` + global `MouseArea` for marquee
- Binds to `ColumnSplitter.getModels()` (via context property)
- Signals to `AppBridge`: `showContextMenu`, `startDrag`, `handleDrop`, `selectPath`
- **Inline Rename:** `F2` triggers `Loader` using reusable `RenameField.qml`.
- **Properties:** `currentSelection` (exposed to Python), `pathBeingRenamed`

---

#### `ui/qml/components/SelectionModel.qml` — Selection State
Path-based selection tracking.

- `select(path)`, `deselect(path)`, `toggle(path)`, `clear()`
- `isSelected(path)` → bool
- Property: `selection` (list of paths)

---

#### `ui/qml/components/RubberBand.qml` — Marquee Selection
Visual rubber band rectangle.

- Properties: `startX`, `startY`, `endX`, `endY`
- Uses `SelectionHelper.getMasonrySelection()` (via context property)

---

### 1.8. Entry Point

#### `main.py` — Bootstrap (minimal)
- Creates `QApplication`
- Instantiates `MainWindow`
- Handles SIGINT for graceful exit

---

### 1.9. Reference: Dragonfly Helpers (`assets/dflynav-src/`)

Legacy patterns for future adaptation. **Not active code.**

| File | Pattern | Adapt For |
|:-----|:--------|:----------|
| `Df_Job.py` | Job queue + history | Operation log UI |
| `Df_Find.py` | Threaded search | `search.py` stub |
| `Df_Config.py` | QSettings persistence | Window state save |
| `Df_Panel.py:559-636` | History stack | Back/Forward nav |

See `usefulness.md` for full analysis.

---

## 2. Architecture Overview

### 2.1. Component Hierarchy
```
[SHELL] MainWindow (QMainWindow)
   ├── Managers: ActionManager, FileManager, ViewManager, NavigationManager
   ├── Components: Toolbar, Sidebar, StatusBar
   ↓
[TABS] TabManager (QTabWidget)
   └── [TAB] BrowserTab (QWidget)
       ├── Scanner (Per-Tab)
       ├── ColumnSplitter (Per-Tab, Layout)
       ├── AppBridge (Per-Tab, QML Bridge)
       ↓
       [VIEW] MasonryView.qml
           ├── Layout: ColumnSplitter
           ├── Controller: AppBridge -> Global Managers
   ↓
[CORE] Backend (Shared)
   ├── I/O: GioBridge (Scanner, Volumes, Bookmarks)
   ├── Ops: TransManager -> FileOperations (QThreadPool)
   └── Media: ThumbnailProvider (GnomeDesktop)
```

### 2.2. Dependency Flow
Dependencies flow **downwards** only.
- `ui/` -> Managers -> Components -> Models -> `core/`

### 2.3. Component Status

- ✅ `ActionManager`, `FileManager`, `ViewManager`, `NavigationManager` — VERIFIED
- ✅ `MainWindow`, `TabManager`, `MasonryView` — VERIFIED
- ✅ `ProgressOverlay`, `StatusBar`, `FileScanner`, `ThumbnailProvider` — VERIFIED
- ✅ `ConflictDialog`, `PropertiesDialog` — VERIFIED
- ✅ `FileOperations`, `TransactionManager` — VERIFIED
- ✅ `SearchWorker`, `UndoManager` — IMPLEMENTED
- ⏳ `DetailView` — TODO

---

## 3. Maintenance Guidelines (CRITICAL)

1.  **Verification Status**: NEVER mark a component or feature as `✅ VERIFIED` unless the USER has explicitly confirmed it works on their machine. Use `🚧 PENDING VERIFICATION` or `✅ IMPLEMENTED` instead.
2.  **Architecture**: New components must not break the top-down dependency flow (`ui` -> `models` -> `core`).
3.  **Async**: All I/O must remain non-blocking. No synchronous specific calls in the main thread.

---

## 4. Safety Mechanisms

### 4.1. Dangerous Operations

| Operation | Risk | Mitigation |
|:----------|:-----|:-----------|
| `Gio.File.trash()` | MED | Uses Trash (recoverable) |
| File Move/Copy | MED | ConflictDialog (Skip/Overwrite/Rename) |
| Directory Merge | HIGH | `do_move` catches `WOULD_MERGE` -> Recursive Merge |
| File Delete | HIGH | **Not implemented.** Trash only. |

### 4.2. Conflict Resolution
- **Where:** `ConflictResolver` in `conflict_dialog.py`
- **When:** Before copy/move/rename if destination exists
- **Options:** Skip / Overwrite / Rename / Cancel All + "Apply to all"
- **Modes:**
  - Copy: `file (Copy).txt`
  - Rename: `file (2).txt`

### 4.3. Error Handling
- Source missing → Skip with console log
- Gio failure → `operationError` signal → shown in overlay

### 4.4. Validation Gates

| Gate | Purpose | Called Before |
|:-----|:--------|:--------------|
| Path exists check | Verify file/folder exists | Any file operation |
| Source exists check | Prevent op on deleted file | Paste, Drop |
| Permission check | Verify read/write access | Rename, Trash |
| Destination Check | Prevent silent overwrite | Rename, Move, Copy |

### 4.5. Privilege Escalation
**None.** Imbric runs as user-level only. No sudo/pkexec.

---

## 4. Data Flows

### 4.1. Inline Rename
```
1. User presses F2 -> MasonryView activates TextInput
2. User types new name + Enter -> AppBridge.renameFile(old, new)
3. AppBridge -> ConflictResolver.resolve_rename()
   - If conflict: show ConflictDialog (User chooses Rename/Overwrite/Cancel)
   - If Rename: generate "file (2).txt"
4. FileOperations.rename() -> Background Thread (Gio)
5. operationCompleted signal -> MainWindow._on_op_completed()
6. AppBridge.selectPath(new_path) -> QML SelectionModel updated
```

### 4.2. Paste Operation
```
1. Ctrl+V → ActionManager triggers FileManager.paste_to_current()
2. FileManager.get_clipboard_files(), is_cut_mode()
3. ConflictResolver.resolve() for each file:
   - CANCEL ALL → break
   - SKIP → continue
   - OVERWRITE/RENAME → FileOperations.copy() or move()
4. Clear clipboard if cut + all succeeded
```

---

## 5. Historical Decisions

- **Hybrid Architecture:** Pure QML lacked native feel → Widgets for desktop behavior
- **Split-Column Layout:** True Masonry slow in Python → Round-robin is instant
- **"God Object" MouseArea:** Per-item handlers caused z-order conflicts
- **GnomeDesktop Thumbnails:** Shared cache with Nautilus, faster
- **QThreadPool over asyncio:** Gio uses GLib's event loop (not asyncio). Python asyncio doesn't help.

---

## 5.1. Threading & Async Patterns

> **Key Insight:** Gio's `*_async()` methods use GLib's event loop, NOT Python's asyncio.
> Since Qt runs its own event loop, we use Qt threading primitives with synchronous Gio calls.

### Pattern Matrix

| Component | Pattern | Why |
|:----------|:--------|:----|
| `FileOperations` | QThreadPool + QRunnable | Parallel ops, per-job cancel |
| `ThumbnailProvider` | QThreadPool + QRunnable | Many concurrent thumbs |
| `ItemCountWorker` | QThreadPool + QRunnable | Background counting |
| `FileScanner` | Gio.enumerate_children_async | True GLib async (works via callback) |
| `SearchWorker` | QThread (subclass) | Long-running subprocess (`fd`) |

### Why Not Python asyncio?

```
Qt Event Loop ──→ Active (QApplication.exec())
GLib Event Loop ──→ NOT running (callbacks never fire)
asyncio Event Loop ──→ NOT running (would need integration)
```

**Result:** Gio's `copy_async()`, `move_async()` callbacks never fire in a Qt app.

### Why Not gbulb (GLib+asyncio bridge)?

Possible but adds dependency. Current approach is simpler:
- Use synchronous Gio in worker threads
- Qt handles thread management via QThreadPool

### Signal Emission from Threads

Use `QMetaObject.invokeMethod()` with `Qt.QueuedConnection` for thread-safe signals:

```python
QMetaObject.invokeMethod(
    self.signals, "finished",
    Qt.QueuedConnection,
    Q_ARG(str, job_id),
    Q_ARG(bool, success)
)
```

### Search Architecture

| Engine | Use Case | Status |
|:-------|:---------|:-------|
| `fd` (fdfind) | Fast path discovery | ✅ Active (Primary) |
| `os.scandir` | Fallback (Pure Python) | ✅ Active (Fallback) |
| `scandir-rs` | Native performance | 📋 Planned (Optimization) |
| `ripgrep` | Content search | 📋 Planned |

- **Current State:** Hybrid `fd` + `os.scandir` via `SearchWorker`.
- **Planned:** Migration to `scandir-rs` to remove subprocess overhead and provide rich metadata (size, dates) without extra `stat` calls.
- **Inline Rename in QML:** Used QML `TextInput` over Widget to maintain scroller sync and visual cohesion.
- **Smart Rename Logic:** Windows-style numbering `(2)` for renames vs `(Copy)` for duplicates.

**Platform Quirk:** Non-GNOME DEs may lack `gir1.2-gnomedesktop` → Fallback needed [TODO]

---

## 6. AI Session Notes

### 6.1. Recent Updates (v0.7.4-alpha)

- **Critical Bug Fixes (2026-01-31):** Resolved Race Conditions in file workers via Atomic Retry Loops. Hardened `UndoManager` with robust asynchronous tracking to prevent state desync. Fixed disconnected `Scanner` signals for directory counts. Verified all via isolated test suites.
- **Navigation System (2026-01-30):** Full Back/Forward/Path management via `NavigationManager`. History stacks integrated with `MainWindow` updates.
- **System Stability (2026-01-29):** Resolved "RAM Explosion" and memory leaks in `FileScanner` caused by shared icon caching and zombie recursion. Optimized QML bindings for performance.
- **Feature-Centric Refactor (2026-01-28):** Finalized transition from technical models to capability-centric Managers (`ui/managers/`). Cleaned up legacy `ShortcutsModel`, `ClipboardManager`, and `SelectionHelper`.
- **Backend Hardening (2026-01-27):** Fixed critical safety bugs in `TransactionManager` (conflict resolution logic) and `file_workers.py` (permission errors and absolute path calculation for Undo).

### 6.2. Session Retrospective (Critical Engineering Failures)

**Key Lessons (Preserved for History):**
1.  **Z-Order Regression:** Adding a full-screen `MouseArea` ("God Object" for selection) accidentally blocked interaction with underlying components (Context Menu, Text Input) because it was declared *after* the ScrollView.
    *   *Fix:* Ensure overlay `MouseAreas` handle pass-through or explicit focus properly.
    *   *Future:* Split interactions into separate layers or components.
2.  **Code Loss:** `AppBridge.showBackgroundContextMenu` was deleted during a `replace_file_content` operation on `renameFile`.
    *   *Fix:* Always verify adjacent methods when replacing chunks.
3.  **Focus Fighting:** `F2` logic split between `rubberBandArea` (global) and `TextInput` (local) caused "dead keys".
    *   *Fix:* Centralized Key handling in the `Root` item to catch bubbling events from anywhere.
    *   *Fix:* Explicit `forceActiveFocus` required when destroying QML components (Loader) to prevent focus drifting to "nowhere".

