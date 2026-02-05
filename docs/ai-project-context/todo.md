# Imbric TODO

> **Convention:** `[x]` done, `[/]` in progress, `[ ]` pending  
> **Bugs:** See `BUGS_AND_FLAWS.md`

---

## Active



---

### General Maintenance

- [ ] **Search UI** — Add Sort/Filter options to right-click background menu
- [ ] **Search UI** — Implement QML Search Bar with `SearchWorker` integration



- [ ] Async thumbnail generation (background thread) - *In Progress*
- [ ] Sort options context menu

### Pending Tests

- [ ] **Drag & Drop**: Verify DnD works with refactored input handlers
- [ ] **Rubberband Selection**: Verify marquee selection on empty space
- [ ] **Right-Click Menus**: Context menu on items and background
- [ ] **Parallel Ops Manual**: Copy large file + trash small file simultaneously

---

## Refactor: Status Bar + Folder Selection

**Goal:** When selecting a folder, show its child count in status bar (Nautilus-style).

- [ ] Refactor `StatusBar.updateSelection` to accept item metadata (not just paths)
- [ ] When a single folder is selected, display: `"'FolderName' selected (containing N items)"`
- [ ] Connect `scanner.fileAttributeUpdated` to update status bar when count arrives
- [ ] Backend (`count_worker.py`) is already done — just needs UI wiring

### 🧩 UI & Navigation Features (Next Up)

- [ ] **Job History UI** (Transaction Log)
  - Backend: `core/transaction_manager.py` (Done)
  - Frontend: Needs list view of past operations + Undo button
- [ ] **Navigation History** (Back/Forward)
  - Backend: Needs `NavigationStack`
  - Frontend: Back/Forward buttons in header

---

## Backlog

- [ ] File Preview (Spacebar fullscreen)
- [ ] Keyboard Navigation (Native ListView Arrow keys)
- [ ] EXIF/Metadata Panel
- [ ] Symlink overlay icons


### Conflict Dialog Improvements (post-alpha)

- [ ] Replace "Overwrite" with "Merge Folders" + "Replace Folder" options
- [ ] Show file count preview ("Folder contains N files, M will conflict")
- [ ] Add "Keep Both" option (auto-rename to "A (1)")
- [ ] Clarify "Apply to all" checkbox behavior (folders vs files)
- [ ] Show file-level conflicts for transparency
- [ ] Add expandable "Show Details" for granular control

### Dragonfly Adaptations (post-bugfix)

- [x] Search impl (`Df_Find.py` → `search.py`)
- [ ] Window state persist (`Df_Config.py` → QSettings)

---

## Technical Debt

| Icon theming | Non-image items need proper icons |
| Error fallbacks | Scanner/Provider graceful degradation |
| Unit tests | None yet |
| Aspect cache | CRITICAL: Required for `JustifiedView` row packing |

---


  - **What Was Tested:**
    - ✅ Engine Detection: `get_search_engine()` correctly returns `FdSearchEngine` when `fd` is installed.
    - ✅ FdSearchEngine: Streams results via `python3 -m core.search_worker ~ ".py$"`.
    - ✅ Batched Emission: Confirmed batches of 50 items emitted.
    - ✅ Import Chain: `AppBridge` imports `SearchWorker` successfully.
  - **What Is NOT Tested:**
    - [ ] **ScandirSearchEngine Fallback:** Simulate missing `fd` and verify `os.scandir` fallback works.
    - [ ] **Cancel Mid-Search:** Start a long search, call `.cancel()`, verify it stops immediately.
    - [ ] **Special Characters:** Filenames with spaces, unicode (e.g., `photo 日本.jpg`), and quotes.
    - [ ] **Permission Errors:** Scanning `/root` or locked folders — should skip gracefully, not crash.
    - [ ] **Empty Results:** Pattern that matches nothing — should emit `searchFinished(0)`.
    - [ ] **Broken Symlinks:** Should not crash, should skip or report error.
    - [ ] **Very Large Directories:** Performance test on `~` (100k+ files) — verify UI doesn't freeze.
    - [ ] **Unit Tests:** Create `tests/test_search.py` with automated pytest cases.
  - **Priority:** HIGH — Should be tested before shipping QML Search Bar.
- [ ] **RapidFuzz Fuzzy Matching (Backlog)**
  - **What:** Fuzzy string matching library for "fzf-style" search (e.g., typing `"img prov"` finds `"ImageProvider.py"`).
  - **Benefits:**
    - Matches partial words, abbreviations, and typos.
    - Returns results ranked by similarity score.
    - Power-user feature loved by devs (VS Code Ctrl+P, fzf).
  - **Cons:**
    - Slower than exact match (must score all filenames).
    - May return unexpected results (`cat` matches `concatenate.py`).
    - Adds dependency (~2MB).
  - **Implementation:**
    
      1. Add `rapidfuzz` to `requirements.txt`.
    
      2. Modify `SearchWorker`: if pattern has no wildcards (`*`, `?`), treat as fuzzy query.
    
      3. Run `fd` with empty pattern → Get all filenames → `process.extract(query, names)` → Return top N.
    
      4. Add toggle in UI: "Fuzzy mode" checkbox or auto-detect.
  - **Priority:** LOW — Nice-to-have, not critical for photo browsing. Excellent for codebase navigation.
- [ ] **Content Search (ripgrep Integration) — Backlog**
  - **What:** Search *inside* text files for content (like `grep`). Nemo has this feature.
  - **Why ripgrep:**
    - Rust-based, extremely fast (faster than `grep`).
    - Available on Linux (`apt install ripgrep`) and Termux (`pkg install ripgrep`).
    - Same "subprocess stdout" integration pattern as `fd`.
  - **Python Options:**
    
      1. **`python-ripgrep`** — PyPI binding, last updated 2021 (possibly stale).
    
      2. **`ripgrepy`** — Newer wrapper, but still just subprocess under the hood.
    
      3. **Direct subprocess** (Recommended) — Same approach as `fd`. Run `rg "query" /path`, parse stdout.
  - **Implementation:**
    
      1. Create `ContentSearchEngine` in `core/search.py`.
    
      2. Wrap `rg` subprocess, fallback to `grep` if `rg` not found.
    
      3. Add `content_search()` slot to `AppBridge`.
    
      4. Add UI toggle: "Search in file contents" checkbox.
  - **Priority:** LOW — Most file managers don't have this. Power-user feature.
- [ ] **Date/Size Filter Support — Backlog**
  - **What:** Filter search results by file size or modification date.
  - **Why:** `fd` already supports this natively (`--size +10M`, `--changed-within 1week`).
  - **Implementation:**
    
      1. Extend `FdSearchEngine.search()` to accept `size_filter` and `date_filter` params.
    
      2. Add UI controls (dropdown/input) in Search Bar for size/date constraints.
  - **Priority:** LOW — Nice-to-have, easy to add later.
- [ ] **Search Within Specific Folder — Backlog**
  - **What:** Allow user to pick a starting folder for search (not always current path).
  - **Implementation:**
    
      1. Add folder picker button next to search bar.
    
      2. Pass selected folder to `SearchWorker.start_search()`.
  - **Priority:** LOW — Current behavior (search from current path) is reasonable default.
- [x] **Trash Management** (`core/file_operations.py` + `core/trash_workers.py`)
  - [x] Implement `trash()` with `NOT_SUPPORTED` / `PERMISSION_DENIED` graceful handling
  - [x] Implement `restore()` (scan `trash:///`, match `trash::orig-path`, newest-first)
  - [x] Implement `listTrash()` (enumerate with metadata)
  - [x] Implement `emptyTrash()` (recursive delete)
  - [x] `trashNotSupported` signal for UI fallback prompt
- [x] **Transaction Manager & Conflict Architecture** <!-- id: 5 -->
  - [x] `TransactionManager`: Handle `conflictDetected` signals.
  - [x] `TrashManager`: Update `restore` to support `overwrite` and `rename_to` parameters.
  - [x] `TrashManager`: Emit rich conflict metadata instead of generic error.
  - [ ] `UI`: Connect `TransactionManager` to `ConflictDialog` for "Resume/Retry" flow.
- [x] **Trash Management Testing**
  - [x] Basic trash & restore (`tests/test_trash_behavior.py`)
  - [x] Duplicate handling (restore newest by date)
  - [x] External drive trash (`.Trash-$UID` directory handled by Gio)
  - [x] Permission denied fallback prompt (Verified in Stress Test)
  - [x] Empty trash performance (Verified in Stress Test)

### Missing Core Stubs

- [x] `ui/models/file_properties_model.py` (Properties Dialog backend) - *Moved from core*
- [x] `core/search.py` (Implemented: FdSearchEngine, ScandirSearchEngine, SearchWorker)
- [x] `ui/models/shortcuts_model.py` (Centralized keybinds) - *Moved from core*
- [x] `core/undo_manager.py` (Implemented: async-aware undo/redo logic, transaction support)
- [x] `core/transaction_manager.py` (Implemented and Integrated)

---

## ✅ Recently Completed (v0.5 - v0.7.4)

### Core Backend
- [x] **Transaction Manager:** Conflict resolution, Pause/Resume, and Undo/Redo backend logic complete.
- [x] **Trash Management:** Full `trash://` support (List, Restore, Empty) with permission fallbacks.
- [x] **Parallel I/O:** `QThreadPool` architecture for all file operations (Copy/Move/Trash).
- [x] **Search Engine:** Hybrid `fd` (subprocess) + `os.scandir` (fallback) backend.
- [x] **Sorting:** Natural sort with folders-first logic.

### UI Safety & Feedback
- [x] **Error Feedback:** `ProgressOverlay` handles partial failures (`PARTIAL:N`) without vanishing.
- [x] **Visuals:** Async thumbnail generation via `QQuickAsyncImageProvider`.
- [x] **Navigation:** `NavigationManager` implemented (Back/Forward logic).

### Refactoring
- [x] **Managers:** Migrated to `ui/managers/` (Action, File, View, Navigation).
- [x] **Stubs:** Completed implementation of `undo_manager.py`, `file_properties_model.py`.

---

## 📉 Low Priority / Nice-to-Have

- [ ] **Templates Support** (`~/Templates` → Context Menu)
- [ ] Archive Management (Zip/Tar support)

## 🚫 Out of Scope

- [ ] Drive Management (Mounting/Unmounting/Formatting) - *Use GNOME Disks*

---

## Missing File Manager Features

- [ ] Back/Forward navigation buttons
- [ ] Free space indicator in status bar
- [ ] Tooltip on folder hover (show child count)
- [ ] List view (alternative to grid)
- [x] Undo/Redo for file operations (backend done, UI pending)
- [x] Search within folder (backend done, UI pending)

---

