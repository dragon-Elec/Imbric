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

> **Version:** 0.3-alpha | **Updated:** 2026-01-18 | **Status:** Active  
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

#### `core/file_operations.py` — Async File I/O (315 lines)
Non-blocking file ops via QThread + Gio.Cancellable. Progress throttled 10Hz.
**Feature:** Return path/message in `operationCompleted` for post-op logic (e.g. selection).

- `FileOperations` (Controller):
  - `copy(src, dest)`, `move(src, dest)`, `trash(path)`, `trashMultiple(paths)`
  - `rename(path, name)` — smart rename flow handled by bridge
  - `createFolder(path)`, `cancel()`, `shutdown()`
  - `openWithDefaultApp(path)` — sync, launches via `Gio.AppInfo`
- `_FileOperationWorker` (QThread):
  - `do_copy()`, `do_move()`, `do_trash()`, `do_rename()`, `do_create_folder()`
  - `_recursive_copy()` — manual folder recursion with progress
  - `_recursive_move_merge()` — manual folder merge (fallback for Error 29 WOULD_MERGE)
  - `_progress_callback()` — throttled to 10Hz
- **Signals:** `operationStarted`, `operationProgress(qint64)`, `operationCompleted(type, path, result)`, `operationError`

---

#### `core/gio_bridge/scanner.py` — Async Directory Enum (127 lines)
True async file listing via `Gio.enumerate_children_async`. Batches of 50.

- `FileScanner`:
  - `scan_directory(path)` — starts async scan
  - `_fetch_next_batch()` — recursive batch fetch
  - `_on_files_retrieved()` — filters hidden, reads image dimensions via `QImageReader`
- **Signals:** `filesFound(list[dict])`, `scanFinished()`, `scanError(str)`

---

#### `core/gio_bridge/bookmarks.py` — GTK Bookmarks (53 lines)
Parses `~/.config/gtk-3.0/bookmarks`.

- `BookmarksBridge.get_bookmarks()` → `[{name, path, icon}]`

---

#### `core/gio_bridge/volumes.py` — Mounted Volumes (35 lines)
Wraps `Gio.VolumeMonitor`.

- `VolumesBridge.get_volumes()` → `[{name, path, icon, type}]`

---

#### `core/image_providers/thumbnail_provider.py` — Thumbnails (132 lines)
`QQuickImageProvider` using GNOME shared cache.

- `ThumbnailProvider.requestImage(id_path, size, requestedSize)`:
  - Check `~/.cache/thumbnails/` via `GnomeDesktop.DesktopThumbnailFactory`
  - Generate if missing
  - **Fallbacks:** Folder icon → MimeType icon → Original image (slow)
- `_get_themed_icon()` — helper for system icons

---

#### `core/clipboard_manager.py` — System Clipboard (148 lines)
Qt clipboard wrapper for Copy/Cut/Paste. GNOME-compatible MIME.

- `copy(paths)` / `cut(paths)` — set clipboard with `x-special/gnome-copied-files` marker
- `getFiles()` → `list[str]` paths from clipboard
- `isCut()` → checks GNOME marker, defaults to copy if missing
- `hasFiles()`, `clear()`
- **Formats:** `text/uri-list` + `x-special/gnome-copied-files`

---

#### `core/selection_helper.py` — Rubberband Geometry (76 lines)
Hit-testing for Masonry layout selection.

- `getMasonrySelection(splitter, col_count, col_width, spacing, x, y, w, h)` → `list[paths]`
- Replicates Masonry layout math (virtualized ListView can't query off-screen)

---

#### `core/file_monitor.py` — Directory Watcher (126 lines)
`Gio.FileMonitor` wrapper for live directory changes.

- `watch(path)` — start monitoring
- `stop()` — cancel monitoring
- **Signals:** `fileCreated`, `fileDeleted`, `fileChanged`, `fileRenamed`, `directoryChanged`

---

### 1.2. UI Models (`ui/models/`)

#### `ui/models/app_bridge.py` — QML-Python Controller (350 lines)
Central bridge exposing Python logic to QML context.

- `startDrag(paths)` — initiates system DnD with MIME data
- `handleDrop(urls, dest)` — processes drops with **ConflictResolver** [MED risk]
- `openPath(path)` — triggers navigation
- `showContextMenu(paths)` — native `QMenu` over QML
- `showBackgroundContextMenu()` — empty space menu (Paste, New Folder, Select All)
- `paste()` — clipboard paste with conflict resolution [MED risk]
- `renameFile(old, new)` — inline rename with specific conflict logic (Rename vs Overwrite)
- `selectPath(path)` — programmatically select file (post-rename)
- `zoom(delta)` — adjusts `targetCellWidth`
- **Properties:** `targetCellWidth` (bound to QML)

---

#### `ui/models/column_splitter.py` — Masonry Layout (150 lines)
"Card Dealing" algorithm — splits files into N columns round-robin.

- `SimpleListModel` — read-only model for one column
  - Roles: `name`, `path`, `isDir`, `width`, `height`
- `ColumnSplitter`:
  - `setColumnCount(n)` — rebuilds models
  - `setFiles(list)` / `appendFiles(list)` — distributes items
  - `getModels()` → `list[SimpleListModel]`
  - `getAllItems()` → master list (for SelectionHelper)
  - `_redistribute()` — core dealing: `columns[i % N].append(file)`

---

#### `ui/models/sidebar_model.py` — Sidebar Data (61 lines)
Combines bookmarks + volumes for sidebar QTreeView.

- `SidebarModel`: merges `BookmarksBridge` + `VolumesBridge`
- `refresh()` — reloads from both sources
- Roles: `name`, `path`, `icon`, `type`

---

### 1.3. UI Main (`ui/`)

#### `ui/main_window.py` — Application Shell (423 lines)
`QMainWindow` with native Fusion style, toolbar, sidebar, QML view.

- `setup_ui()` — builds toolbar, sidebar, path bar, QQuickView
- `navigate_to(path)` — triggers scan + monitor
- `go_up()` — parent directory
- `change_zoom(delta)` — adjusts target column width
- `_recalc_columns()` — calculates optimal column count from width
- `_on_op_completed(type, path, result)` — handles post-op logic (e.g. re-selection)
- **Shortcuts (ApplicationShortcut):** Ctrl+C/X/V, Delete, Ctrl+=/−
- `_on_copy_triggered()`, `_on_cut_triggered()`, `_on_paste_triggered()`, `_on_trash_triggered()`
- `eventFilter()` — detects resize for column recalc
- `closeEvent()` — clean worker shutdown

---

### 1.4. UI Widgets (`ui/widgets/`)

#### `ui/widgets/progress_overlay.py` — File Op Feedback (165 lines)
Nautilus-style slide-up overlay. Shows only if op > 300ms.

- `onOperationStarted(type, path)` — shows with delay
- `onOperationProgress(path, current_qint64, total_qint64)`
- `onOperationCompleted(type, path, result)` / `onOperationError()` — hides
- **Signal:** `cancelRequested`

---

#### `ui/widgets/status_bar.py` — Item Counts (85 lines)
Bottom bar: "X items (Y folders, Z files)" or "X items selected".

- `updateItemCount(files)` — accumulates batch counts
- `updateSelection(paths)` — shows selection count
- `resetCounts()` — clears on navigation

---

### 1.5. UI Widgets (`ui/widgets/`)

#### `ui/widgets/tab_manager.py` — Multi-Tab Browser [NEW]
Wraps `QTabWidget` with per-tab state.

- `TabManager`: Manages tabs, New/Close signals.
- `BrowserTab`:
  - Owns `FileScanner`, `ColumnSplitter`, `SelectionHelper`, `AppBridge`.
  - Embeds `MasonryView.qml` via `createWindowContainer`.
  - Handles `showEvent` (layout fix) and path navigation.

---

### 1.6. UI Dialogs (`ui/dialogs/`) [NEW]

#### `ui/dialogs/conflict_dialog.py` — File Conflict Resolution (212 lines)
Modal dialog for paste/drop/rename conflicts.

- `ConflictAction` (Enum): `SKIP`, `OVERWRITE`, `RENAME`, `CANCEL`
- `ConflictDialog(QDialog)`:
  - Buttons: Skip / Overwrite / Rename / Cancel All
  - Checkbox: "Apply to all"
- `ConflictResolver` (Shared Logic):
  - `resolve(src, dest)` → Copy mode `(Copy)`, `(Copy 2)`
  - `resolve_rename(old, new)` → Rename mode `(2)`, `(3)`
  - `_resolve_internal(template)` — Unified logic core
  - `_generate_unique_name(template)` — Handles numbering vs copy suffix

---

### 1.6. QML (`ui/qml/`)

#### `ui/qml/views/MasonryView.qml` — GPU Grid
Main photo grid with N `ListView` columns.

- **Input Model:** Hybrid — per-delegate `TapHandler`/`DragHandler` + global `MouseArea` for marquee
- Binds to `ColumnSplitter.getModels()`
- Signals to `AppBridge`: `showContextMenu`, `startDrag`, `handleDrop`
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
- Uses `SelectionHelper.getMasonrySelection()` for hit testing

---

### 1.7. Entry Point

#### `main.py` — Bootstrap (minimal)
- Creates `QApplication`
- Instantiates `MainWindow`
- Handles SIGINT for graceful exit

---

## 2. Architecture Overview

### 2.1. Component Hierarchy
```
[ENTRY] main.py
   ↓
[SHELL] MainWindow (QMainWindow + Fusion)
   ├── Toolbar, Sidebar (QTreeView + SidebarModel)
   ├── StatusBar, ProgressOverlay
   ↓
[TABS] TabManager (QTabWidget)
   └── [TAB] BrowserTab (QWidget)
       ├── Scanner, Splitter, SelectionHelper (Per-Tab)
       ↓
       [VIEW] MasonryView.qml (QQuickView container)
           ├── Layout: ColumnSplitter (Round-Robin)
           ├── Controller: AppBridge (Drag, Drop, Menu, Rename)
   ↓
[CORE] Backend (Shared)
   ├── I/O: GioBridge (Scanner, Volumes, Bookmarks)
   ├── Ops: FileOperations (QThread + Gio.Cancellable)
   └── Media: ThumbnailProvider (GnomeDesktop)
```

### 2.2. Dependency Flow
Dependencies flow **downwards** only.
- `ui/` → `ui/models/` → `core/`
- No circular imports

### 2.3. Component Status Map

| Component | Location | Status |
|:----------|:---------|:-------|
| MainWindow | `ui/main_window.py` | ✅ VERIFIED |
| TabManager | `ui/widgets/tab_manager.py` | ✅ VERIFIED |
| MasonryView | `ui/qml/views/` | ✅ VERIFIED |
| RubberBand | `ui/qml/components/` | ✅ VERIFIED |
| SelectionModel | `ui/qml/components/` | ✅ VERIFIED |
| ProgressOverlay | `ui/widgets/` | ✅ VERIFIED |
| StatusBar | `ui/widgets/` | ✅ VERIFIED |
| ConflictDialog | `ui/dialogs/` | 🚧 PENDING VERIFICATION |
| FileOperations | `core/` | ✅ VERIFIED |
| ClipboardManager | `core/` | ✅ VERIFIED |
| FileScanner | `core/gio_bridge/` | ✅ VERIFIED |
| ThumbnailProvider | `core/image_providers/` | ✅ VERIFIED |
| DetailView | `ui/qml/views/` | ⏳ TODO |
| Inline Rename | `MasonryView.qml` / `AppBridge` | 🚧 PENDING VERIFICATION |
| Undo/Redo | — | ⏳ TODO |

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

### 3.2. Conflict Resolution
- **Where:** `ConflictResolver` in `conflict_dialog.py`
- **When:** Before copy/move/rename if destination exists
- **Options:** Skip / Overwrite / Rename / Cancel All + "Apply to all"
- **Modes:**
  - Copy: `file (Copy).txt`
  - Rename: `file (2).txt`

### 3.3. Error Handling
- Source missing → Skip with console log
- Gio failure → `operationError` signal → shown in overlay

### 3.4. Validation Gates

| Gate | Purpose | Called Before |
|:-----|:--------|:--------------|
| Path exists check | Verify file/folder exists | Any file operation |
| Source exists check | Prevent op on deleted file | Paste, Drop |
| Permission check | Verify read/write access | Rename, Trash |
| Destination Check | Prevent silent overwrite | Rename, Move, Copy |

### 3.5. Privilege Escalation
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
1. Ctrl+V → _on_paste_triggered()
2. ClipboardManager.getFiles(), isCut()
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
- **QThread over asyncio:** Proper cancellation via `Gio.Cancellable` (verified)
- **Inline Rename in QML:** Used QML `TextInput` over Widget to maintain scroller sync and visual cohesion.
- **Smart Rename Logic:** Windows-style numbering `(2)` for renames vs `(Copy)` for duplicates.

**Platform Quirk:** Non-GNOME DEs may lack `gir1.2-gnomedesktop` → Fallback needed [TODO]

---

## 6. AI Session Notes

### 6.1. Session: 2026-01-18 (Phase 5 - Interactions)

**Completed:**
- **Inline Rename:** Implemented F2 / Context Menu rename with in-place editing.
- **Smart Conflict Handling:** Unified conflict logic. Added "Rename" styling `(2)` vs `(Copy)`.
- **Async Verification:** Confirmed `Gio` async enumeration + `QThread` file ops = True non-blocking.
- **Selection Persistence:** Files remain selected after renaming.

**Refactoring:**
- Consolidated `ConflictResolver` logic into `_resolve_internal` to share code between Copy/Rename modes.
- Renamed "Cancel" to "Cancel All" in conflict dialog for clarity.

### 6.2. AI Observations (User Preferences)

- **Visual Style:** GTK-like aesthetics — padding, flat borders, native icons
- **"Lens not Engine":** Applies to UI too — mimic native shell as close as possible
- **Keybinds:** Should match Nautilus conventions
- **Code Organization:** Extract bridges/controllers, avoid "God classes" in MainWindow
- **Naming:** User prefers specific, native-aligned naming over generic
- **Safety:** Explicit confirmation for overwrites, no silent failures.
- **Architecture:** User is asking about splitting QML `delegate` code into separate files (concern about "God Object" files).

### 6.3. Known Bugs & TODO

| Issue | Severity | Status |
|:------|:---------|:-------|
| **Shift-Click Range Selection** | MED | ✅ IMPLEMENTED |
| **Ctrl-Click Multi-Select** | MED | ✅ IMPLEMENTED |
| **Undo / Redo** | MED | ❌ MISSING |
| **Inline Rename F2 Focus** | LOW | ⚠️ WONTFIX — See [BUG-F2-Focus-Loss.md](BUG-F2-Focus-Loss.md) |
| **Cut Dimming + Paste Highlight** | LOW | ✅ IMPLEMENTED |
| **New Folder + Auto-Select** | LOW | ✅ IMPLEMENTED |
| Drag Cursor Feedback (+/→) | LOW | ✅ Qt handles automatically |
| File Preview (Spacebar/Click) | LOW | ⏳ TODO |
| Move directory over directory | MED | 🐛 OPEN |
| Symlink Thumbnail Icons | LOW | ⏳ TODO (Nautilus shows link overlay) |

### 6.3.1. Pending Tests (Next Session)

- [ ] **Drag & Drop**: Verify DnD still works after input refactor
- [ ] **Rubberband Selection**: Verify marquee selection on empty space
- [ ] **Right-Click Menus**: Context menu on items and background
- [ ] **Dir-over-Dir Bug**: Reproduce and investigate

### 6.4. Session History

| Date | Focus | Changes |
|:-----|:------|:--------|
| 2026-01-19 | **New Folder** | Fixed path, added auto-numbering, auto-select after creation |
| 2026-01-19 | **Paste Highlight** | Pasted files now auto-selected after operation completes |
| 2026-01-19 | **Multi-Select Fix** | Moved click handling to MouseArea (modifier visibility), refactored SelectionModel (Nautilus-style logic), fixed anchor reset on clear |
| 2026-01-19 | **Quick Wins** | Cut Dimming (partial), Shift-Click (broken), F2 debug cleanup |
| 2026-01-19 | **Input Refactor** | Per-delegate TapHandler/DragHandler, simplified marquee, F2 workaround (Enter-only) |
| 2026-01-18 | **Inline Rename** | F2 Rename, Smart Conflict Logic, Async Verification, Context Menu Fixes |
| 2026-01-18 | **Multi-Tab** | TabManager, Separation of Concerns, Crash Fixes |
| 2026-01-18 | **Layout** | Fixed Masonry aspect ratio (square icons) |
| 2026-01-18 | **I/O Logic** | Conflict dialog, shortcut/clipboard fixes |
| 2026-01-17 | Async I/O | QThread file ops, ProgressOverlay |
| 2026-01-17 | Interactions | Selection, DnD, Context Menu |

### 6.5. Session Retrospective (Lessons Learned)

**Critial Engineering Failures & Fixes:**
1.  **Z-Order Regression:** Adding a full-screen `MouseArea` ("God Object" for selection) accidentally blocked interaction with underlying components (Context Menu, Text Input) because it was declared *after* the ScrollView.
    *   *Fix:* Ensure overlay `MouseAreas` handle pass-through or explicit focus properly.
    *   *Future:* Split interactions into separate layers or components.
2.  **Code Loss:** `AppBridge.showBackgroundContextMenu` was deleted during a `replace_file_content` operation on `renameFile`.
    *   *Fix:* Always verify adjacent methods when replacing chunks.
3.  **Focus Fighting:** `F2` logic split between `rubberBandArea` (global) and `TextInput` (local) caused "dead keys".
    *   *Fix:* Centralized Key handling in the `Root` item to catch bubbling events from anywhere.
    *   *Fix:* Explicit `forceActiveFocus` required when destroying QML components (Loader) to prevent focus drifting to "nowhere".

