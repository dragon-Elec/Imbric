# Imbric: Architecture & State Reference

> **Version:** 0.2-alpha  
> **Last Updated:** 2026-01-17  
> **Status:** Active Development  
> **Target Platform:** Linux (GNOME-based: Zorin, Ubuntu, Fedora)  
> **Primary Stack:** Python 3.10+ / PySide6 (Qt6) / QML

---

## Quick Context (For Fresh Sessions)

**What:** Photo-first file manager with Masonry layout, native GNOME integration.

**Current Phase:** Phase 5 (Async I/O). Non-blocking file operations with progress overlay.

**Critical Context:**
- Uses `Gio` for file ops, `GnomeDesktop` for thumbnails — NOT Python reimplementations
- Masonry = "Card Dealing" into N columns, not position calculation
- **Input Handling:** "God Object" pattern — Single global MouseArea handles all clicks/drags.
- **Hybrid Menus:** QML emits signal → Python shows native `QMenu`.
- Linux-only. No cross-platform abstraction.

**Blockers:** None

---

## Table of Contents

1. [Project Vision & Goals](#1-project-vision--goals)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Core Modules](#3-core-modules)
4. [Interface/UI Layer](#4-interfaceui-layer)
5. [Data Flow & Patterns](#5-data-flow--patterns)
6. [Safety & Critical Paths](#6-safety--critical-paths)
7. [Known Issues & Historical Context](#7-known-issues--historical-context)
8. [AI Session Notes](#8-ai-session-notes)

---

## 1. Project Vision & Goals

### 1.1. Core Purpose

Imbric is a **lens** for your filesystem, not a file manager built from scratch. It provides a high-performance, photo-centric view of directories using native Linux libraries. The goal: make browsing 5000+ photos as smooth as scrolling a feed.

### 1.2. Design Philosophy

| Principle | Implication |
|:----------|:------------|
| **"Lens, not Engine"** | Defer to OS libs (`Gio`, `GnomeDesktop`). Python = glue only. |
| **Photo-First** | Masonry layout is default. Aspect ratios matter. |
| **Native Speed** | No Python math for layout. Let Qt's C++ `Column` handle it. |
| **GNOME Integration** | Share thumbnail cache with Nautilus. Read GTK bookmarks. |

### 1.3. Non-Goals (Explicit Exclusions)

- ❌ Cross-platform support (No Windows/macOS)
- ❌ Full file manager feature parity (focus on viewing, not power-user ops)
- ❌ Cloud storage integration (local filesystem only)
- ❌ Custom thumbnail generation (use system thumbnails)

### 1.4. Target Users

- **Primary:** Photo enthusiasts on Linux who want fast visual browsing
- **Secondary:** Developers tired of slow thumbnail loading in Nautilus for large folders

---

## 2. High-Level Architecture

### 2.1. Directory Structure

```
imbric/
├── [ENTRY]    main.py                   # Initializes QApplication, starts MainWindow
│
├── [CORE]     core/                     # Backend logic (Python → GNOME)
│   ├──        gio_bridge/               # Wrappers for GLib I/O
│   │   ├──    bookmarks.py              # Reads ~/.config/gtk-3.0/bookmarks
│   │   └──    volumes.py                # Gio.VolumeMonitor wrapper
│   ├──        image_providers/          # Thumbnail generation (Direct GnomeDesktop usage)
│   ├──        file_operations.py        # [NEW] Trash, Move, Copy, Open (via Gio)
│   ├──        clipboard_manager.py      # [NEW] System Clipboard (Copy/Cut/Paste)
│   ├──        selection_helper.py       # [NEW] Geometry Hit-Testing for Masonry
│   └──        file_monitor.py           # [NEW] Gio.FileMonitor wrapper
│
├── [UI]       ui/                       # Frontend (Qt Widgets + QML)
│   ├──        main_window.py            # Native Shell (QMainWindow, Toolbar, Sidebar, Shortcuts)
│   ├──        models/                   # QAbstractListModel implementations
│   │   ├──    sidebar_model.py          # Bookmarks + Volumes for sidebar
│   │   ├──    column_splitter.py        # "Card Dealing" logic for Masonry
│   │   └──    app_bridge.py             # [NEW] QML-Python Controller (Drag, Drop, Menu)
│   └──        qml/
│       ├──    views/
│       │      ├── MasonryView.qml       # High-performance grid with Selection & DnD
│       │      └── DetailView.qml        # [FUTURE] Fullscreen image viewer
│       └──    components/               # [NEW] Reusable QML UI elements
│              ├── RubberBand.qml        # Selection marquee
│              ├── SelectionModel.qml    # Path-based selection state
│              └── qmldir                 # Library manifest
│   └──        widgets/                  # [NEW] Python Qt widgets
│              ├── progress_overlay.py   # Non-blocking file op progress
│              ├── status_bar.py         # [NEW] Status bar with item counts
│              └── qmldir                 # Library manifest
│
├── [ASSET]    assets/                   # Template files only
│
└── [DOC]      docs/                     # Structure, TODO, archive
    ├──        ai-project-context/       # THIS FOLDER
    └──        archive/                  # Legacy QML Shell files
```

### 2.2. Dependency Flow (Hybrid)

```
┌─────────────────────────────────────────────────────────────┐
│                 MainWindow (Python / Widgets)               │
│   Native Shell, Toolbar, Sidebar                            │
└───────────────────────────┬─────────────────────────────────┘
                            │ embeds via QWidget.createWindowContainer
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   QQuickView (QML)                          │
│   MasonryView.qml (Hardware Accelerated)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ binds to
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    ui/models/ (Bridge)                      │
│   ColumnSplitter, SidebarModel, AppBridge                   │
└───────────────────────────┬─────────────────────────────────┘
                            │ imports
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    core/ (Python Logic)                     │
│   gio_bridge/, image_providers/                             │
│   FileOperations, ClipboardManager, SelectionHelper         │
└─────────────────────────────────────────────────────────────┘
```

### 2.3. External Dependencies

| Dependency | Purpose | Version | Notes |
|:-----------|:--------|:--------|:------|
| `PySide6` | Qt6 Python bindings | 6.x | pip install |
| `PyGObject` | GLib/Gio bindings | System | `apt install python3-gi` |
| `gir1.2-gnomedesktop-3.0` | Thumbnail factory | System | `apt install` |

---

## 3. Core Modules

### 3.1. `core/gio_bridge/bookmarks.py` — GTK Bookmark Reader

**Status:** [VERIFIED: 2026-01-15]

**Purpose:** Parse `~/.config/gtk-3.0/bookmarks` into a list of sidebar entries.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `BookmarksBridge` | `get_bookmarks() → list[dict]` | Returns `[{name, path, icon}]` | LOW |

**Internal Logic:**
1. Read file line by line
2. Parse `file:///path Name` format
3. URL-decode path, extract basename if no name
4. Return dict list

**Dependencies:** None (stdlib only)

---

### 3.2. `core/gio_bridge/volumes.py` — Mounted Volumes Monitor

**Status:** [VERIFIED: 2026-01-15]

**Purpose:** Use `Gio.VolumeMonitor` to list mounted drives (USBs, partitions).

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `VolumesBridge` | `get_volumes() → list[dict]` | Returns `[{name, path, icon, type}]` | LOW |

**Dependencies:** `gi.repository.Gio`

---

### 3.3. `ui/models/sidebar_model.py` — Qt Model for Sidebar

**Status:** [VERIFIED: 2026-01-15]

**Purpose:** QAbstractListModel that combines bookmarks + volumes for QML sidebar.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `SidebarModel` | `refresh()` | Reload bookmarks and volumes | LOW |

**Roles Exposed to QML:** `name`, `path`, `icon`, `type`

**Dependencies:** `PySide6.QtCore`, `core/gio_bridge/*`

---

### 3.4. `core/file_operations.py` — File System Operations

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Non-blocking file operations using QThread + Gio.Cancellable.

**Architecture:**
- `_FileOperationWorker`: Internal worker running in QThread
- `FileOperations`: Public controller class

**Key Exports:**

| Method | Purpose | Blocking | Risk |
|:-------|:--------|:---------|:-----|
| `copy(src, dest)` | Copy file/folder | NO | MED |
| `move(src, dest)` | Move file/folder | NO | MED |
| `trash(path)` | Move to Trash | NO | MED |
| `trashMultiple(paths)` | Trash multiple files | NO | MED |
| `rename(path, name)` | Rename file/folder | NO | MED |
| `cancel()` | Cancel current op | NO | LOW |
| `openWithDefaultApp(path)` | Launch with default app | YES | LOW |

**Signals:**
- `operationStarted(op_type, path)`
- `operationProgress(path, current, total)` (uses qint64)
- `operationCompleted(op_type, path)`
- `operationError(op_type, path, message)`

**Threading Model:**
- **Controller:** (Main Thread) Emits `_request*` signals to Worker.
- **Worker:** (Background Thread) Executes I/O and emits progress.
- **Throttling:** Progress updates limited to 10Hz to prevent UI freeze.

**Dependencies:** `gi.repository.Gio`, `PySide6.QtCore.QThread`

---

### 3.5. `core/clipboard_manager.py` — System Clipboard

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Manage copy/cut/paste state using the system clipboard.

**Key Exports:**

| Method | Purpose | Risk |
|:-------|:--------|:-----|
| `copy(paths)` | Set clipboard to copy mode | LOW |
| `cut(paths)` | Set clipboard to cut mode | LOW |
| `getFiles()` | Retrieve files from clipboard | LOW |
| `hasFiles()` | Check if clipboard has files | LOW |
| `isCut()` | Check if cut operation | LOW |

**Dependencies:** `PySide6.QtGui.QClipboard`, `PySide6.QtCore.QMimeData`

---

### 3.6. `core/selection_helper.py` — Masonry Hit Testing

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Provides geometry calculations for the Masonry layout to determine which items are within a rubberband selection rectangle.

**Key Exports:**

| Method | Purpose | Risk |
|:-------|:--------|:-----|
| `getMasonrySelection(splitter, cols, colW, gap, x, y, w, h)` | Return list of paths within rect | LOW |

**Dependencies:** `PySide6.QtCore.QObject`

---

### 3.7. `ui/models/app_bridge.py` — QML-Python Controller

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Acts as the central controller for QML interactions, bridging high-level commands to Python backend.

**Key Exports:**

| Method | Purpose | Risk |
|:-------|:--------|:-----|
| `openPath(path)` | Navigate to directory | LOW |
| `showContextMenu(paths)` | Show native QMenu for selection | LOW |
| `startDrag(paths)` | Initiate system drag-and-drop | LOW |
| `handleDrop(urls, dest)` | Process dropped files (Auto-rename duplicates) | MED |
| `paste()` | Paste from clipboard (Auto-rename duplicates) | MED |

**Dependencies:** `PySide6.QtWidgets.QMenu`, `PySide6.QtGui.QDrag`

---


### 3.8. `core/gio_bridge/scanner.py` — Async File Scanner

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Asynchronously enumerates files in a directory using Gio, retrieving metadata (name, type, hidden status) in batches.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `FileScanner` | `scan_directory(path)` | Starts async scan | LOW |
| — | `filesFound` (Signal) | Emits batch of `[{name, path, isDir, w, h}]` | LOW |
| — | `scanFinished` (Signal) | Emits when all files scanned | LOW |

**Internal Logic:**
1. Uses `Gio.File.enumerate_children_async` for non-blocking I/O.
2. Fetches files in batches (default 50) using `next_files_async`.
3. Filters hidden files.
4. Reads image dimensions using `QImageReader` (fast header read) for non-directories.
5. Emits `filesFound` incrementally to populate UI while scanning.

**Dependencies:** `gi.repository.Gio`, `PySide6.QtGui.QImageReader`

---

### 3.9. `core/file_monitor.py` — Directory Watcher

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Watches a specific directory for filesystem changes (create, delete, rename) using `Gio.FileMonitor`.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `FileMonitor` | `watch(path)` | Starts monitoring path | LOW |
| — | `stop()` | Stops monitoring | LOW |
| — | `fileCreated`, `fileDeleted` | Signals for change events | LOW |

**Internal Logic:**
1. Wraps `Gio.File.monitor_directory`.
2. Translates raw GIO events (`moved_in`, `renamed`, etc.) into clean Qt signals.
3. Used to trigger a refresh of the `FileScanner` or updating the model directly (future).

**Dependencies:** `gi.repository.Gio`

---

### 3.10. `core/image_providers/thumbnail_provider.py` — Thumbnail Generator

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Custom `QQuickImageProvider` that generates/retrieves thumbnails using GNOME's system-wide thumbnailer.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `ThumbnailProvider` | `requestImage(id, size, reqSize)` | Returns `QImage` for path | MED |

**Internal Logic:**
1. Receives request `image://thumbnail//path/to/file.jpg`.
2. Checks GNOME thumbnail cache (`~/.cache/thumbnails/`) using `GnomeDesktop.DesktopThumbnailFactory`.
3. If missing, attempts to generate a new thumbnail via `GnomeDesktop`.
4. Fallbacks:
   - If folder: Returns themed folder icon.
   - If image load fails: Returns themed file icon.
   - If generation fails: Loads original image (slow fallback).

**Dependencies:** `gi.repository.GnomeDesktop`, `PySide6.QtQuick.QQuickImageProvider`

---

### 3.11. `ui/models/column_splitter.py` — Masonry Layout Engine

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** The "Dealer" logic that splits a flat list of files into N columns to achieve a Masonry layout.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `ColumnSplitter` | `setFiles(list)` | Sets master list and deals | LOW |
| `ColumnSplitter` | `setColumnCount(n)` | Re-deals into N columns | LOW |
| `ColumnSplitter` | `getModels()` | Returns list of `SimpleListModel` | LOW |
| `SimpleListModel` | — | Read-only list model for one column | LOW |

**Internal Logic:**
1. **Round-Robin Dealing:** Iterates input list, assigning item `i` to column `i % N`.
2. **Models:** Maintains N `SimpleListModel` instances.
3. On change, clears and repopulates all N models.
4. Preserves chronological order (top-left to bottom-right reading direction).

**Dependencies:** `PySide6.QtCore.QAbstractListModel`

---

### 3.12. `main.py` — Application Entry Point

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Bootstraps the PySide6 application, sets up the Python instance, and launches the main window.

**Key Exports:** N/A (Script)

**Internal Logic:**
1. Initializes `QApplication`.
2. Instantiates `MainWindow`.

---

### 3.13. `ui/widgets/status_bar.py` — File Count & Selection Status

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Custom `QStatusBar` widget that displays live folder statistics and selection counts.

**Key Exports:**

| Class | Method | Purpose | Risk |
|:------|:-------|:--------|:-----|
| `StatusBar` | `updateItemCount(files)` | Accumulates batch counts | LOW |
| `StatusBar` | `updateSelection(int)` | Updates "X items selected" | LOW |
| `StatusBar` | `resetCounts()` | Clears counters (on nav) | LOW |

**Internal Logic:**
1. Maintains `_total_items`, `_folder_count`, `_file_count`.
2. Updates accumulatively as `FileScanner` emits batches.
3. Switches text between "X folders, Y files" and "Z items selected".

**Dependencies:** `PySide6.QtWidgets`

---

### 3.14. `ui/widgets/progress_overlay.py` — Async Operation Feedback

**Status:** [VERIFIED: 2026-01-17]

**Purpose:** Slide-up overlay at the bottom of the window showing progress for long-running file operations.

**Key Exports:**

| Class | Slots | Purpose | Risk |
|:------|:-----|:--------|:-----|
| `ProgressOverlay` | `onOperationStarted` | Shows overlay (delayed) | LOW |
| `ProgressOverlay` | `onOperationProgress` | Updates bar (via qint64) | LOW |
| `ProgressOverlay` | `onOperationCompleted` | Hides overlay | LOW |

**Internal Logic:**
1. **Throttled Display:** Uses 300ms timer to avoid flashing for quick ops.
2. **Visuals:** Shows icon (Copy/Move/Trash), text, and progress bar.
3. **Safety:** Connects to `qint64` signals to handle >2GB files.

**Dependencies:** `PySide6.QtWidgets`, `core/file_operations.py`
3. Sets up signal handling (SIGINT) for polite exit on Ctrl+C.
4. Executes the Qt event loop.

**Dependencies:** `PySide6.QtWidgets`, `ui/main_window.py`

---

## 4. Interface/UI Layer

### 4.1. Interface Type

**Type:** GUI (Desktop Application)  
**Framework:** Qt6 via PySide6 + QML

### 4.2. Component Map

| Component | Location | Purpose | Status |
|:----------|:---------|:--------|:-------|
| `Main.qml` | `ui/qml/Main.qml` | Root window with SplitView | [ARCHIVED] |
| `MainWindow` | `ui/main_window.py` | Native Shell (Toolbar, Sidebar, Shortcuts) | [VERIFIED] |
| `MasonryView` | `ui/qml/views/` | High-performance grid w/ Selection & DnD | [VERIFIED] |
| `RubberBand` | `ui/qml/components/` | Selection Marquee | [VERIFIED] |
| `SelectionModel` | `ui/qml/components/` | Path-based Selection State | [VERIFIED] |
| `ProgressOverlay` | `ui/widgets/` | Non-blocking file op progress (Throttled) | [VERIFIED] |
| `StatusBar` | `ui/widgets/` | Item count & Selection status | [VERIFIED] |
| `DetailView` | `ui/qml/views/` | [FUTURE] Fullscreen image viewer | [TODO] |
| `SearchBar` | `ui/qml/components/` | [FUTURE] Global search input | [TODO] |


### 4.3. Navigation

```
ApplicationWindow (MainWindow)
├── Sidebar (Left)            → SidebarModel
│   └── QTreeView             → Click emits (path)
│
└── Content (Central)         → QQuickView (MasonryView)
    ├── Grid State            → ColumnSplitter (Model)
    └── [FUTURE] Detail View  → Fullscreen Overlay (ImageModel)
```

### 4.4. Visual Engineering: "The Smart Fusion" Strategy

We achieve a modern, native Linux look *without* using non-standard libraries (like KDE Frameworks) by applying a modernization layer on top of the standard Qt **Fusion** style.

**The Problem:**
Standard Qt widgets (Fusion style) look "safe" but dated—hard borders, small padding, and lack of elevation.

**The Solution:**
We use a 3-layer styling approach:

1.  **Style Base:** `QStyleFactory.create("Fusion")`
    *   Provides the correct logic (hits, focus rects) but generic visuals.
2.  **System Binding:** `activePalette` (Python)
    *   We do *not* hardcode colors. We bind Qt's `QPalette` to the system's `activePalette` (from GTK/GNOME).
    *   Dark Mode works automatically because Qt reads the OS text/window colors.
3.  **QSS Patching:** `ui/styles/modern.qss`
    *   **Flatness:** We remove the 1px `border` from Toolbars and TreeViews.
    *   **Padding:** We inject `6px` padding into lists (up from default ~2px) to match GTK4 spatial density.
    *   **Radius:** We enforce `border-radius: 6px` on input fields and buttons.
    *   **Palette Roles:** We use CSS variables like `background: palette(window)` instead of hex codes. This ensures the QSS "recolors" itself instantly when the system theme changes.

**Key Implementation Details:**
*   **PathBar:** A `QLineEdit` styled as a pill (`border-radius: 6px`).
*   **Sidebar:** A `QTreeView` stripped of its frame (`border: none`) with `::item` padding increased to `6px 4px`.
*   **Zoom:** Toolbar buttons use standard `QIcon.fromTheme()` (e.g., `zoom-in`, `go-up`) to pull the active icon pack (Adwaita, Papirus, etc.).

---

## 5. Data Flow & Patterns

### 5.1. Key Workflow: Directory Navigation

```
1. [QML Sidebar] → User clicks bookmark
2. [Signal]      → folderSelected(path) emitted
3. [Python]      → FileScanner.scan_async(path) via Gio
4. [Python]      → Sorter.sort(files, criterion)
5. [Python]      → ColumnSplitter.deal(sorted_files, N)
6. [Python]      → N × ColumnModel updated
7. [QML]         → N × ListView auto-updates
```

### 5.2. State Management

**Pattern:** Model-based (QAbstractListModel)  
**Location:** `ui/models/*.py`  
**QML State:** Minimal. Data flows from Python models.

### 5.3. The "Card Dealing" Algorithm

**Purpose:** Distribute files into N columns for Masonry layout.

```python
def deal(files: list, num_columns: int) -> list[list]:
    columns = [[] for _ in range(num_columns)]
    for i, file in enumerate(files):
        columns[i % num_columns].append(file)
    return columns
```

**Why Round-Robin:** Preserves chronological order left-to-right.

---

## 6. Safety & Critical Paths

### 6.1. Dangerous Operations

| Operation | Location | Risk | Mitigation |
|:----------|:---------|:-----|:-----------|
| `Gio.File.trash()` | `core/file_operations.py` | MED | Uses Trash, not rm. |
| File Move | `core/file_operations.py` | MED | Overwrites if dest exists. |
| File rename | [FUTURE] | MED | Validate name, check conflicts |
| File delete | — | HIGH | **Never implemented.** Only Trash. |

### 6.2. Validation Gates

| Gate | Purpose | Called Before |
|:-----|:--------|:--------------|
| Path validation | Ensure path exists | Any file op |
| Permission check | Verify read/write | Rename, Trash |

### 6.3. Privilege Escalation

**Method:** None. Imbric operates as user-level. No sudo/pkexec.

---

## 7. Known Issues & Historical Context

### 7.1. Active Issues

| ID | Summary | Severity | Status |
|:---|:--------|:---------|:-------|
| — | None documented yet | — | — |

### 7.2. Historical Decisions

| Decision | Context | Date | Implication |
|:---------|:--------|:-----|:------------|
| Split-Column over true Masonry | Qt Column layout is C++, instant. Added aspect-ratio logic to fix layout. | 2026-01-15 | Ragged bottom acceptable. |
| GnomeDesktop for thumbnails | Shared cache with Nautilus | 2026-01-15 | Requires `gir1.2-gnomedesktop-*` |
| Linux-only | Enables Gio/GNOME deep integration | 2026-01-15 | No cross-platform abstraction |

### 7.3. Platform Quirks

| Platform | Issue | Workaround |
|:---------|:------|:-----------|
| Non-GNOME DEs | May lack `gir1.2-gnomedesktop` | Fallback thumbnail gen needed [AI-TODO] |

---

## 8. AI Session Notes

### 8.1. Last Session Summary

**Date:** 2026-01-17 (Evening)  
**Focus:** Async File Operations & Progress UI
**Outcome:**
- **QThread Refactor:** Rewrote `FileOperations` to use QThread + Gio.Cancellable.
- **Non-blocking I/O:** All file ops (copy, move, trash) now run in background thread.
- **Progress Overlay:** Created Nautilus-style progress indicator at bottom of window.
- **Cancellation Support:** Operations can be cancelled via Gio.Cancellable.
- **Clean Shutdown:** Added `closeEvent` to properly shutdown worker thread.

**Known Bugs:**
1. File Preview not implemented (Clicking image does nothing).
2. Inline Rename not implemented.

**Next Steps:**
- Test file operations on actual UI. [DONE]
- Implement Inline Rename.
- Implement File Preview / Detail View.

### 8.2. Session Update: Robust File Operations (Late Night)
**Focus:** Fix UI freezes and crashes during I/O.
**Outcome:**
1.  **Threading Fixed:** Converted `FileOperations` to usage Signals/Slots. Direct method calls were blocking main thread.
2.  **Stability:** Updated signals to `qint64` to fix `OverflowError` on >2GB files.
3.  **Recursive Copy:** implemented manual recursion for folder copying.
4.  **UX Polish:** Throttled progress signals (10Hz) and tuned overlay delay (300ms).

**Status:** Code is now stable and responsive under load.

### 8.6. Session History (Partial)

| Date | Focus Area | Key Changes |
|:-----|:-----------|:------------|
| 2026-01-17 | Async I/O | QThread file ops, ProgressOverlay widget |
| 2026-01-17 | Interactions | Selection, DnD, Context Menu, Shortcuts |
| 2026-01-16 | Interactions | Implemented Zoom (Toolbar + Ctrl-Scroll + Keyboard) |
| 2026-01-16 | Visual Polish | Smart Material QML + "GTK-like" Sidebar styling |
| 2026-01-16 | Debugging | Fixed Thumbnail visibility (removed faulty `MultiEffect`) |
| 2026-01-15 | Performance | Jitter fix, Hardware Acceleration, True Aspect Ratios |

### 8.7. Architecture Decisions
- **Why Hybrid?** Pure QML lacked native "feel" for menus/sidebar. Widgets gives us standard desktop behavior for free.
- **Why not MultiEffect?** It caused total rendering failure on the specific target hardware. Switched to `clip: true` for safe, performant rounded corners.
- **Why "God Object" MouseArea?** Individual item MouseAreas created z-order conflicts (clicks vs rubberband). A single overlay resolves this cleanly.
- **Why Hybrid Context Menu?** QML menus don't match GTK. Python `QMenu` provides native look-and-feel.
- **Why QThread over asyncio?** QThread + Gio.Cancellable gives proper cancellation and progress callbacks. asyncio.to_thread() doesn't support mid-operation cancellation.

### 8.8. AI Observations
- User prefers visually polished "GTK-like" aesthetics (padding, flat borders).
- "Lens not engine" applies to UI too: mimic the native shell (Fusion/GTK) as close as possible.
- User prefers specific, native-aligned implementation (e.g. keybinds matching Nautilus) over generic solutions.
- User values code organization (extracting `AppBridge`, avoiding "God classes" in MainWindow).


```
