# Imbric: Architecture & State Reference

> **Version:** 0.1-alpha  
> **Last Updated:** 2026-01-15  
> **Status:** Active Development  
> **Target Platform:** Linux (GNOME-based: Zorin, Ubuntu, Fedora)  
> **Primary Stack:** Python 3.10+ / PySide6 (Qt6) / QML

---

## Quick Context (For Fresh Sessions)

**What:** Photo-first file manager with Masonry layout, native GNOME integration.

**Current Phase:** Phase 3 Complete. Working on Phase 4 (Interactions).

**Critical Context:**
- Uses `Gio` for file ops, `GnomeDesktop` for thumbnails — NOT Python reimplementations
- Masonry = "Card Dealing" into N columns, not position calculation
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
├── [ENTRY]    main.py              # Initializes QApplication, starts MainWindow
│
├── [CORE]     core/                # Backend logic (Python → GNOME)
│   ├──        gio_bridge/          # Wrappers for GLib I/O
│   │   ├──    bookmarks.py         # Reads ~/.config/gtk-3.0/bookmarks
│   │   └──    volumes.py           # Gio.VolumeMonitor wrapper
│   ├──        image_providers/     # Thumbnail generation (Direct GnomeDesktop usage)
│   └──        gnome_utils/         # [FUTURE] Standalone GnomeDesktop wrappers (Refactor target)
│
├── [UI]       ui/                  # Frontend (Qt Widgets + QML)
│   ├──        main_window.py       # [NEW] Native Shell (QMainWindow, Toolbar, Sidebar)
│   ├──        models/              # QAbstractListModel implementations
│   │   └──    sidebar_model.py     # Bookmarks + Volumes for sidebar
│   └──        qml/
│       ├──    views/
│       │      ├── MasonryView.qml  # [EMBEDDED] High-performance grid
│       │      └── DetailView.qml   # [FUTURE] Fullscreen image viewer
│       └──    components/          # [FUTURE] Reusable QML UI elements
│
├── [ASSET]    assets/              # Template files only
│
└── [DOC]      docs/                # Structure, TODO, archive
    ├──        ai-project-context/  # THIS FOLDER
    └──        archive/             # Legacy QML Shell files
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
│   ColumnSplitter, SidebarModel                              │
└───────────────────────────┬─────────────────────────────────┘
                            │ imports
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    core/ (Python Logic)                     │
│   gio_bridge/, image_providers/                             │
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

## 4. Interface/UI Layer

### 4.1. Interface Type

**Type:** GUI (Desktop Application)  
**Framework:** Qt6 via PySide6 + QML

### 4.2. Component Map

| Component | Location | Purpose | Status |
|:----------|:---------|:--------|:-------|
| `Main.qml` | `ui/qml/Main.qml` | Root window with SplitView | [ARCHIVED] |
| `MainWindow` | `ui/main_window.py` | Native Shell (Toolbar, Sidebar) | [VERIFIED] |
| `MasonryView` | `ui/qml/views/` | High-performance photo grid | [VERIFIED] |
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
| `Gio.File.trash_async()` | [FUTURE] | MED | User confirmation dialog |
| File rename | [FUTURE] | MED | Validate name, check conflicts |
| File delete | [FUTURE] | HIGH | **Never implement rm**. Only Trash. |

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

**Date:** 2026-01-15  
**Focus:** Hybrid Architecture & Performance
**Outcome:**
- **Hybrid Refactor:** Migrated Shell to `QMainWindow` (Qt Widgets) for native look/feel.
- **Performance:** Fixed `QQuickWidget` jitter by switching to `QQuickView` + `createWindowContainer`.
- **Masonry Layout:** Implemented true aspect-ratio sizing by reading image headers in `scanner.py`.
- **Navigation:** Implemented native Sidebar and Toolbar with "Up" navigation.

**Known Bugs:**
1. File Preview not implemented (Clicking image does nothing).
2. Resize lag (minor) check known trade-offs.

**Next Steps:**
- Pick up "File Preview" from Backlog when ready.

### 8.2. Session History (Partial)

| Date | Focus Area | Key Changes |
|:-----|:-----------|:------------|
| 2026-01-15 | Performance | Jitter fix, Hardware Acceleration, True Aspect Ratios |
| 2026-01-15 | Architecture | Hybrid Stack (Widgets + QML) |
| 2026-01-15 | Foundation | Scanner, Splitter, ThumbnailProvider |

### 8.3. Architecture Decisions
- **Why Hybrid?** Pure QML lacked native "feel" for menus/sidebar. Widgets gives us standard desktop behavior for free.
- **Why QQuickView?** `QQuickWidget` software rendering was too slow/jittery for large grids. `createWindowContainer` gives direct GPU access.

### 8.4. AI Observations
- User prefers "lens not engine" philosophy — use GNOME libs, don't reimplement
- Documentation should be visual (ASCII diagrams, tables)
- User wants Fusion/Breeze style (Qt6 Breeze not available in repos, using Fusion)
- Always ask before making changes

### 8.5. Pending Investigations
- [ ] [AI-TODO] Async thumbnail generation thread (Priority)

```
