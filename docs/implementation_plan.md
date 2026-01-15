# Imbric - Application Blueprint (Smart Build)

## Goal Description
Imbric is a high-performance, photo-centric File Manager (FM) designed specifically for the Linux (GNOME) ecosystem. It leverages existing OS-level libraries into a modern PySide6/QML interface to achieve native speed without complex low-level code.

## Tech Stack
- **Language:** Python 3.x
- **GUI Framework:** Qt6 via PySide6
- **UI Language:** QML (Qt Quick)
- **Core Libraries (Linux Native):**
    - `Gio` (GLib Input/Output): File operations, volume mounting, bookmarks.
    - `GnomeDesktop` (via GObject Introspection): Native High-Speed Thumbnailing.
- **Target OS:** Linux (Zorin/Ubuntu/GNOME-based). **Not cross-platform.**

## Core Architecture

### 1. The Strategy: "Lens for the Filesystem"
Imbric is not a file manager built from scratch; it is a high-performance *viewer* (lens) for the existing GNOME filesystem.
- **Sorting/Filtering:** Handled by C++ using `QSortFilterProxyModel`.
- **Thumbnails:** Handled by `GnomeDesktop` (shared cache with Nautilus).
- **File Ops:** Handled by `Gio`.

### 2. Masonry Layout: The "Split-Column" Engine
Instead of expensive absolute positioning calculation:
- **Technique:** "Round Robin" Card Dealing.
- **Logic:** Python splits the file list into `N` sub-lists (Columns).
- **Responsive Dealing:** `N` is dynamic. Python listens to Window Width changes. `N = Window Width / Optimal Column Width`. Python "re-deals" the cards when `N` changes.
- **Rendering:** Each sub-list is fed to a standard QML `Column`.
- **Result:** Native scrolling performance, responsive layout, zero complex layout math.

### 3. Directory Structure
```text
imbric/
├── core/               # Backend logic
│   ├── gio_bridge/     # Gio wrappers (Mounts, Trash, Bookmarks)
│   └── gnome_utils/    # GnomeDesktop thumbnail integration
├── ui/                 # Frontend
│   ├── qml/            # Visuals
│   │   ├── components/ # SplitColumn, SidebarItem
│   │   └── views/      # MasonryView (The 3-column layout)
│   └── models/         # QSortFilterProxyModels & ColumnSplitter
├── main.py             # Entry point
```

## Implementation Roadmap

### Phase 1: The Native Shell
- Initialize PySide6 + QML window.
- **CLI Integration:** Parse command line args (`imbric /path/to/folder`) for "Open With" support.
- Implement **Gio Bridge**:
    - Load System Bookmarks (`~/.config/gtk-3.0/bookmarks`) into the Sidebar.
    - List drives/volumes via `Gio.VolumeMonitor`.
    - **Async Scanning:** Ensure file discovery runs on a background thread.

### Phase 2: The "Split-Column" Engine
- Create the **Column Splitter** logic in Python.
- **Ordering Logic:** Implement Sorter (Date/Name/Size) *before* Splitter.
- **Responsive Logic:** Dynamic `N` columns based on window width.
- Implement `QAbstractListModel` for file data.
- "Deal" items into `N` separate models.
- Render with colored rectangles to prove the layout engine.

### Phase 3: The "Gnome" Integration (Thumbnails)
- Integrate `GnomeDesktop.DesktopThumbnailFactory`.
- Create a `QQuickImageProvider` to serve these thumbnails to QML.
- Connect the real file models to the thumbnail provider.

### Phase 4: Interactions & Polish
- **Keyboard Navigation:** Custom logic to jump focus between independent lists (Left/Right arrows).
- Context Menus (Open, Rename, Trash - using `Gio`).
- Drag and Drop (Standard Qt internal & external moving).
- Multi-Tab / Multi-Window support.
