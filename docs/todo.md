# Imbric - Development TODO

> **Purpose:** Single source of truth for project tasks.  
> **Convention:** `[x]` done, `[/]` in progress, `[ ]` pending  
> **Last Updated:** 2026-01-15 (Session 2)

---

## Phase 1: The Native Shell ✓

- [x] Project scaffolding (`main.py`, dirs)
- [x] PySide6 + QML window setup
- [x] CLI argument parsing (`imbric /path`)
- [x] Gio Bridge: Bookmarks reader
- [x] Gio Bridge: Volume monitor
- [x] SidebarModel (Qt model for QML)
- [x] Main.qml with SplitView layout
- [x] SystemPalette for theme awareness
- [x] Fusion style integration

---

## Phase 2: The Split-Column Engine ✓

### Core Logic
- [x] **Async File Scanner** (`core/gio_bridge/scanner.py`)
    - [x] Use `Gio.File.enumerate_children_async()`
    - [x] Emit batches via Qt signals
    - [x] Construct full file paths

- [x] **Column Splitter** (`ui/models/column_splitter.py`)
    - [x] Round-robin "card dealing" algorithm
    - [x] Dynamic column count support
    - [x] `SimpleListModel` per column

- [ ] **Sorting Logic**
    - [ ] Implement `QSortFilterProxyModel`
    - [ ] Sort BEFORE dealing to columns

### QML Implementation
- [x] **MasonryView.qml** (`ui/qml/views/MasonryView.qml`)
    - [x] `Row` of N `ListView`s via Repeater
    - [x] ScrollView wrapper for unified scrolling
    - [x] Image loading with async flag

---

## Phase 3: GNOME Thumbnail Integration ✓

- [x] **ThumbnailProvider** (`core/image_providers/thumbnail_provider.py`)
    - [x] QQuickImageProvider subclass
    - [x] GnomeDesktop.DesktopThumbnailFactory integration
    - [x] Directory detection (skip thumbnailing folders)

- [x] **Fallback Icons**
    - [x] Show folder icon for directories
    - [x] Show generic file icon for non-images

- [ ] **Async Thumbnail Generation**
    - [ ] Move generation to background thread
    - [ ] Return placeholder, reload when ready

---

## Phase 4a: Visual Polish (Material & GTK) ✓

- [x] **Smart Material Engine**
    - [x] Integrate Qt Material Style for QML
    - [x] `modern.qss` for Qt Widgets styling
    - [x] Dynamic System Theme binding
- [x] **MasonryView Logic**
    - [x] Card elevation and animations
    - [x] Rounded corners (Safe clipping)
    - [x] Gradient text overlays
- [x] **Sidebar GTK Styling**
    - [x] Padding (6px) and border removal
    - [x] Modern selection states
- [x] **Toolbar Polish**
    - [x] Breadcrumb/PathBar rounded pill design
    - [x] Zoom Controls (In/Out buttons)
- [x] **Card Interactions**
    - [x] Ctrl+Scroll Zooming (MouseArea Overlay)
    - [x] Keyboard Zoom Shortcuts (Ctrl+/Ctrl-)

---

## Phase 4b: Interactions & Features

## Phase 4: Backlog / Low Priority

### File Interactions
- [ ] **File Preview** (Fullscreen Viewer) - *Low Priority*
- [ ] **Keyboard Navigation** (Arrow keys) - *Low Priority*
- [ ] **Context Menu** (Open, Rename, Trash) - *Low Priority*

### Advanced Layout
- [ ] **Sorting Logic** (Sort by Date/Size) - *Low Priority*
- [ ] **Drag and Drop** - *Low Priority*

---

## Known Bugs 🐛

| ID | Description | Severity | Status |
|----|-------------|----------|--------|
| #001 | ~~Folder boxes show blank~~ - Fixed: Folders now show folder icons | Medium | **Fixed** |
| #002 | **No file opening** - Folder navigation works, but clicking files does nothing | Medium | Open |
| #003 | ~~Aspect ratios simulated~~ - Fixed: Real dimensions used via QImageReader | Low | **Fixed** |
| #004 | ~~MasonryView layout blank~~ - Fixed: Delegates had zero width due to Layout.fillWidth issues | High | **Fixed** |

---

## Stretch Goals
- [ ] Metadata / EXIF Panel
- [ ] Multi-tab support


---

## Technical Debt

| Item | Note |
|------|------|
| Icon theming | Need folder/file icons for non-image items |
| Error handling | Scanner and Provider need graceful fallbacks |
| Unit tests | None yet |
| Aspect ratio cache | Need to read dimensions before layout |

### Performance Notes
*   **Hybrid Architecture (Current):** Uses `QQuickView` embedded via `QWidget.createWindowContainer`.
    *   *Pros:* Native Qt Widgets integration (standard toolbar/sidebar/menus).
    *   *Cons:* Slight resize lag on some systems compared to Pure QML due to window container sync.
*   **Pure QML (Alternative):** ~20% faster resizing, but requires re-implementing all native widgets in QML. Considered for future prototype/RC phase.
