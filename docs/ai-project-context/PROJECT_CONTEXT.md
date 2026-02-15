# Imbric: Architecture & Safety Reference

> **MAINTENANCE GUIDE:** Optimize for **LLM token efficiency + human readability**.
> 
> **Token-Efficient Patterns:**
> 
> - **Bullet lists** > tables (pipes/alignment waste tokens)
> - **Fragment sentences** > prose ("Async enum via Gio" not "This module is used for...")
> - **Common words** tokenize better than rare jargon
> - **Inline code** for identifiers: `copy()`, `Gio.File`
> - **Consistent abbreviations:** MED, LOW, [TODO], [NEW]
> 
> **When to Use Tables:** Only for 3+ columns or structured comparison.
> 
> **Update Rules:** Session notes → Section 8 only. No changelog prose.

> **Version:** 0.7.7-alpha | **Updated:** 2026-02-12 | **Status:** Active  
> **Target:** Linux (GNOME) | **Stack:** Python 3.10+ / PySide6 / QML / Gio / GnomeDesktop
> **Issue Tracking:** See @[todo.md](todo.md) and @[BUGS_AND_FLAWS.md](BUGS_AND_FLAWS.md) for active tasks/bugs.

---

## Quick Context (Fresh Session Start Here)

**What:** Photo-first file manager with Justified Grid layout, native GNOME integration.

**Current Phase:** Phase 6 (Robustness) — Architectural validation and signal hardening.

**Critical Patterns:**

- **"Lens, not Engine":** Defer I/O to `Gio`, thumbnails to `GnomeDesktop`
- **Layout:** Justified Grid — Row-based layout honoring aspect ratios (no cropping)
- **Input:** Hybrid — per-delegate `TapHandler`/`DragHandler` + global `MouseArea` for marquee selection
- **Menus:** Hybrid — QML emits signal → Python shows native `QMenu`

**Dependencies:** `PySide6`, `PyGObject`, `gir1.2-gnomedesktop-3.0`

---

## Development Approach: Stub-First / API-First

> **What is a Stub?** A stub file contains the **complete structure** (classes, functions, docstrings, type hints) but **no implementation** (just `pass` or `raise NotImplementedError`). The API is defined, the "contract" is clear, but the logic is empty.

Why We Use This:

- See all the pieces — Every helper file exists in the codebase, even if not implemented yet
- One thing at a time — Implement one file, test it thoroughly, mark as done, move on
- Self-documenting — Docstrings explain what each function should do
- No surprises — The interface is stable before implementation
- Isolation — Each file does one thing and does it well

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

#### `core/gio_bridge/scanner.py` — Async Directory Enum `[OPTIMIZED]`

True async file listing via `Gio.enumerate_children_async`. Batches of 200.

- `FileScanner`:
  - `scan_directory(path)` — starts async scan
  - `_fetch_next_batch()` — recursive batch fetch
  - `_process_batch()` — filters hidden, queues dimension reading to `DimensionWorker`
  - **Performance:** Debounced emission (100ms) prevents UI thrashing
- **Signals:** `filesFound(session_id, list[dict])`, `scanFinished(session_id)`, `scanError(str)`, `fileAttributeUpdated(path, attr, value)`
- **Session Tracking:** UUID-based sessions prevent cross-talk during rapid navigation

#### `core/gio_bridge/dimension_worker.py` — Async Image Dimension Reader `[NEW]`

Background worker for reading image headers without blocking the main thread.

- `DimensionWorker`:
  - `enqueue(path)` — queues image for header reading via `QThreadPool`
  - `dimensionsReady(path, width, height)` — signal emitted when complete
- **Performance:** Uses `QImageReader` in background threads to prevent UI freezes during folder scanning
- **Race Condition Fix:** Dimensions may arrive before `filesFound` completes; handled by `RowBuilder` pending cache
  
  #### `core/gio_bridge/quick_access.py` — Sidebar Data Aggregator `[NEW]`
  
  Aggregates data for the new QML Sidebar.
  
  - `QuickAccessBridge`:
    - Combines Home, Recent, Standard XDG Dirs, Trash, and Bookmarks.
    - **Async Trash:** Monitors `trash:///` to toggle empty/full icon state.
    - **Signals:** `itemsChanged`.

#### `core/image_providers/theme_provider.py` — Native System Icons `[NEW]`

Unified provider for system theme icons.

- `ThemeImageProvider`: QQuickImageProvider handling `image://theme/` requests.
- Returns pixmaps consistent with system theme (Adwaita/Yaru/etc).

---

#### `core/gio_bridge/bookmarks.py` — GTK Bookmarks

Parses `~/.config/gtk-3.0/bookmarks`.

- `BookmarksBridge.get_bookmarks()` → `[{name, path, icon}]`
  - **Note:** Now primarily consumed by `QuickAccessBridge`.

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
- **Updated:** Now the primary source of truth for UI. Aggregates all worker signals.

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

- Delegates to `RowBuilder` (Layout).

#### `ui/managers/row_builder.py` — Justified Grid Engine `[NEW]`

Core layout engine for the photo grid.

- Implements "Simple Justified" algorithm (Phase 1).
- Handles row packing, aspect ratio scaling, and sorting via `Sorter`.
- Provides `getItemsInRect(x,y,w,h)` for 2D marquee selection.
- **Signals:** `rowsChanged`, `rowHeightChanged`.

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

#### `ui/models/shortcuts.py` — Shortcut Registry `[NEW]`

Centralized keyboard configuration and persistence.

- Pure data model using `QSettings`.
- Enum-based mappings (`ShortcutAction`).
- Conflict detection and default resets.
  
  #### `ui/models/tab_model.py` — Tab State Logic `[NEW]`
  
  Pure Python state for the QML Tab system.
  
  - `TabController`: Represents a single tab.
    - Owns `FileScanner`, `RowBuilder`, `AppBridge`.
    - Manages Navigation Stack (`history_stack`, `future_stack`).
  - `TabListModel`: `QAbstractListModel` exposing tabs to QML.

---

#### `ui/models/sidebar_model.py` — Sidebar Data

- `SidebarModel`: merges `BookmarksBridge` + `VolumesBridge`
- `refresh()` — reloads from both sources
- Roles: `name`, `path`, `icon`, `type`
- **Status:** Legacy/Transitioning. Replaced by `QuickAccessBridge` in new Sidebar.

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


#### `ui/components/tab_manager.py` — Multi-Tab System `[REFACTORED]`
  
  Now a `QML`-based tab system hosted in a `QWidget` via `createWindowContainer`.
  
  - Uses `TabListModel` and `QQuickView`.
  - Loads `ui/qml/views/TabContainer.qml`.
  - **Legacy:** `tab_manager_legacy.py` contains the old `QTabWidget` version.

#### `ui/components/navigation_bar.py` — Toolbar

#### `ui/components/sidebar.py` — Sidebar Widget `[REFACTORED]`
  
  `QQuickWidget` hosting `ui/qml/components/Sidebar.qml`.
  
  - Uses `QuickAccessBridge` and `VolumesBridge` for data.
  - Replaces `QTreeView`.

#### `ui/components/status_bar.py` — Status Feedback

Shows item counts (folders/files) and selection info.

- `updateAttribute(path, attr, value)` — Handles async scanner updates (child counts).
- `setMessage(str)` — Temporary status feedback.
  
  #### `ui/components/progress_overlay.py` — Op Progress
  
  Visual overlay for batch operations. 
- Subscribes to `TransactionManager` signals. 
- Shows progress bars for active batches and individual job details.
- **Signals:** `cancelRequested(str)`.

---

### 1.6. UI Main (`ui/`)

#### `ui/main_window.py` — Application Shell

Orchestrator. Initializes Managers and Components.

- `setup_ui()` — builds structure
- `ActionManager.setup_actions()` — registers shortcuts
- Delegated logic: Zoom -> ViewManager, Ops -> FileManager
- Integrated `Diagnostics` (F12) for memory profiling.

#### `ui/styles/modern.qss` — Global Styles

Application-wide stylesheet for custom widgets and QML integration consistency.

---

### 1.7. QML (`ui/qml/`)

#### `ui/qml/views/JustifiedView.qml` — Justified Grid

Main photo grid with row-based layout.

- **Input Model:** `DragHandler` (Marquee) + `WheelHandler` (Turbo Scroll) + `TapHandler` (Background)
- **Auto-Scroll:** Cubic acceleration logic for smooth edge scrolling.
- Binds to `RowBuilder.getRows()` (via context property)
- Signals to `AppBridge`: `showContextMenu`, `startDrag`, `handleDrop`, `selectPath`
- **Inline Rename:** `F2` triggers `Loader` using reusable `RenameField.qml`.
- **Properties:** `currentSelection` (exposed to Python), `pathBeingRenamed`

#### `ui/qml/components/RowDelegate.qml` — Row Component `[NEW]`

Visual wrapper for a row of `FileDelegate` items.

- Uses `Repeater` to instantiate items within a `Row` layout.
- Injects services (`bridge`, `selModel`) into delegates.
- Handles row-level spacing and height (bound to `imageHeight`).

#### `ui/qml/components/FileDelegate.qml` — Item Component `[EXTRACTED]`

Extracted from JustifiedView for performance and isolation.

- Handles rendering of singular file/folder cards.
- Manages internal state: Hover, Selection visuals, Rename overlay.
- Uses `Loader` for heavy elements (Thumbnails) to improve scrolling performance.

#### `ui/qml/components/RenameField.qml` — Inline Rename `[NEW]`

Reusable QML `TextArea` for file renaming.

- Auto-selects filename (excluding extension) on activation.
- Handles `Enter` (commit) and `Escape` (cancel).
- Styled via system colors.

---

#### `ui/qml/components/SelectionModel.qml` — Selection State

Path-based selection tracking for the QML view.

- Tracks `selection` (array of paths) and `anchorPath` (for shift-range).
- `handleClick(path, ctrl, shift, allItems)`: Implements standard file manager behavior (Nautilus-style).
- `selectRange(paths, append)`: Handles bulk selection from rubberband.
- `selectAll(allItems)`: Global selection.
  
  #### `ui/qml/views/TabContainer.qml` — Tab Layout `[NEW]`
  
  Root for the TabManager QML view.
  
  - Contains `GtkTabBar` (Top) and `StackLayout` (Content).
  - Binds to `tabModel` (C++).
  
  #### `ui/qml/components/GtkTabBar.qml` — Custom Tabs `[NEW]`
  
  A custom, GTK-styled Tab Bar implementation in QML.
  
  - Uses `GtkTabButton` for individual tabs.
  - Supports close buttons, dragging (future), and overflow.
  
  #### `ui/qml/components/Sidebar.qml` — Sidebar View `[NEW]`
  
  QML replacement for the sidebar tree.
  
  - Displays `QuickAccess` items and `Volumes`.
  - Handles mounting/unmounting signals.

---

#### `ui/qml/components/RubberBand.qml` — Marquee Selection

Visual rubber band rectangle.

- **Driven By:** `JustifiedView`'s `DragHandler`.
- **Coordinates:** Visual coordinates updated by handler, which maps to Content coordinates for backend.
- Notifies `SelectionModel` to update selection state.

---

### 1.8. Entry Point

#### `main.py` — Bootstrap (minimal)

- Creates `QApplication`
- Instantiates `MainWindow`
- Handles SIGINT for graceful exit

---



---

## 2. Architecture Overview

### 2.1. Component Hierarchy

```
[SHELL] MainWindow (QMainWindow)
   ├── Managers: ActionManager, FileManager, ViewManager, NavigationManager
   ├── Components: Toolbar, Sidebar (QQuickWidget), StatusBar
   ↓
[TABS] TabManager (QWidget -> QQuickView)
   └── [VIEW] TabContainer.qml (StackLayout)
       └── [TAB] TabController (Python Object)
           ├── Scanner (Per-Tab)
           ├── RowBuilder (Per-Tab, Layout)
           ├── AppBridge (Per-Tab, QML Bridge)
           ↓
           [VIEW] JustifiedView.qml
               ├── Layout: RowBuilder
               ├── Controller: AppBridge -> Global Managers
   ↓
[CORE] Backend (Shared)
   ├── I/O: GioBridge (Scanner, Volumes, QuickAccessBridge)
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

1. **Verification Status**: NEVER mark a component or feature as `✅ VERIFIED` unless the USER has explicitly confirmed it works on their machine. Use `🚧 PENDING VERIFICATION` or `✅ IMPLEMENTED` instead.
2. **Architecture**: New components must not break the top-down dependency flow (`ui` -> `models` -> `core`).
3. **Async**: All I/O must remain non-blocking. No synchronous specific calls in the main thread.

---

## 4. Safety Mechanisms

### 4.1. Dangerous Operations

| Operation          | Risk | Mitigation                                         |
|:------------------ |:---- |:-------------------------------------------------- |
| `Gio.File.trash()` | MED  | Uses Trash (recoverable)                           |
| File Move/Copy     | MED  | ConflictDialog (Skip/Overwrite/Rename)             |
| Directory Merge    | HIGH | `do_move` catches `WOULD_MERGE` -> Recursive Merge |
| File Delete        | HIGH | **Not implemented.** Trash only.                   |

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

| Gate                | Purpose                    | Called Before      |
|:------------------- |:-------------------------- |:------------------ |
| Path exists check   | Verify file/folder exists  | Any file operation |
| Source exists check | Prevent op on deleted file | Paste, Drop        |
| Permission check    | Verify read/write access   | Rename, Trash      |
| Destination Check   | Prevent silent overwrite   | Rename, Move, Copy |

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
- **Justified Grid:** Row-based layout preserves image aspect ratios naturally
- **"God Object" MouseArea:** Per-item handlers caused z-order conflicts
- **GnomeDesktop Thumbnails:** Shared cache with Nautilus, faster
- **No Asyncio:** Gio uses GLib's event loop (not asyncio), which doesn't run in Qt. We use `QThreadPool` + synchronous Gio calls instead.
- **Search Engine:** Hybrid `fd` (fast) + `os.scandir` (fallback). Future: `scandir-rs`.

---



---

## 6. AI Session Notes

### 6.1. Recent Updates (v0.7.8-alpha)

- **Drag & Drop Fix (2026-02-12):** Fixed a critical conflict bug where dragging files into folders failed because the destination path lacked the filename. `FileManager.handle_drop` now correctly appends the source filename to the destination directory.
- **Marquee Selection (2026-02-12):** Implemented visual marquee selection with auto-scroll. Fixed coordinate drift by pinning start point to content coordinates. Added `RowBuilder.getItemsInRect` for optimized hit testing.
- **Auto-Scroll Engine (2026-02-12):** Added cubic acceleration scrolling for drag operations near view edges. `speed = 5 + 60 * intensity^3`.
- **Async Dimensions (2026-02-07):** Eliminated UI freezes during scan by moving image header reading to `DimensionWorker` (QThreadPool). Added `RowBuilder` caching to handle out-of-order dimension updates.
- **Justified Grid (2026-02-05):** Replaced Masonry layout with Row-based Justified Grid (Google Photos style). Honors aspect ratios.
- **Component Extraction (2026-02-02):** Extracted `FileDelegate.qml` from main view for performance and isolation.
- **Icon Rendering (2026-02-01):** Implemented `ThemeImageProvider` for crisp native GTK icons in QML.

### 6.2. Critical Lessons & Decisions

- **Event Loop Reality:** Python `asyncio` is useless here because Gio uses the GLib event loop, which doesn't run in `QApplication`. We use `QThreadPool` + synchronous Gio calls instead.
- **Z-Order Hell:** Beware of "God Object" MouseAreas (like for Marquee) blocking underlying components. Use `z: -1` or specific parenting to avoid stealing clicks.
- **Focus Fighting:** QML `Loader` destruction can cause focus to drift to "nowhere", breaking keyboard shortcuts. Always `forceActiveFocus()` on the view when closing overlays.
- **Path Handling:** Always use `os.path.join(dest_dir, filename)` when moving/copying to a folder. Never presume `Gio` handles directory-as-destination for you.
