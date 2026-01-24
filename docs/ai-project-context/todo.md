# Imbric TODO

> **Convention:** `[x]` done, `[/]` in progress, `[ ]` pending  
> **Bugs:** See `BUGS_AND_FLAWS.md`

---

## Active

### 🚀 Android Device Integration (Experimental Alpha v0.6.0)

**Goal:** MTP device support via `android-file-transfer-linux` Python bindings.

- [ ] **Phase 1: Foundation** (Read-only device browsing)
  - [ ] Install & verify `android-file-transfer-linux` with Python bindings
  - [ ] Test thumbnail support: `ObjectInfo.ThumbFormat`, `ThumbPixWidth`, `ThumbPixHeight`
  - [ ] Create `core/mtp_bridge/` module structure
  - [ ] Implement `MTPDeviceManager` (device detection)
  - [ ] Implement `MTPScanner` (file listing compatible with `FileScanner` API)
  - [ ] Implement `MTPThumbnailProvider` (`get_thumb()` integration)
  - [ ] Modify `MainWindow` for `mtp://` path detection + scanner switching
  - [ ] Modify `SidebarModel` to show "Devices" section
  - [ ] Test with real Android device
- [ ] **Phase 2: Photo Transfer** (v0.7.0)
  - [ ] Implement `MTPFileOperations` (copy from device)
  - [ ] Wire up clipboard operations for MTP → Local copy
  - [ ] Progress tracking for large transfers
- [ ] **Phase 3: Advanced** (Backlog)
  - [ ] Bi-directional sync (upload to device)
  - [ ] Auto-detection on device plug-in
  - [ ] DCIM quick-import ("Import all photos" button)

**Why This Is Unique:** First Linux photo manager with native Android device browsing in same UI as local files!

---

### General Maintenance

- [x] Sorting logic (`sorter.py` — implemented with natural sort, folders-first)
- [ ] Sorting UI — Add sort options to right-click background menu
- [ ] Fix BUG-007: Rubberband selection ignores sort order
- [ ] Async thumbnail generation (background thread)
- [ ] UI Error Feedback — `ProgressOverlay` show `PARTIAL:N` skipped files

---

## Refactor: Status Bar + Folder Selection

**Goal:** When selecting a folder, show its child count in status bar (Nautilus-style).

- [ ] Refactor `StatusBar.updateSelection` to accept item metadata (not just paths)
- [ ] When a single folder is selected, display: `"'FolderName' selected (containing N items)"`
- [ ] Connect `scanner.fileAttributeUpdated` to update status bar when count arrives
- [ ] Backend (`count_worker.py`) is already done — just needs UI wiring

---

## Backlog

- [ ] File Preview (Spacebar fullscreen)
- [ ] Keyboard Navigation (Arrow keys in grid)
- [ ] EXIF/Metadata Panel
- [ ] Symlink overlay icons
- [ ] Column-Major layout option (Pinterest-style, post-alpha)

### Conflict Dialog Improvements (post-alpha)
- [ ] Replace "Overwrite" with "Merge Folders" + "Replace Folder" options
- [ ] Show file count preview ("Folder contains N files, M will conflict")
- [ ] Add "Keep Both" option (auto-rename to "A (1)")
- [ ] Clarify "Apply to all" checkbox behavior (folders vs files)
- [ ] Show file-level conflicts for transparency
- [ ] Add expandable "Show Details" for granular control

### Dragonfly Adaptations (post-bugfix)
- [ ] Search impl (`Df_Find.py` → `search.py`)
- [ ] Job history UI (`Df_Job.py` patterns)
- [ ] Back/Forward nav (`Df_Panel.py` history stack)
- [ ] Window state persist (`Df_Config.py` → QSettings)

---

## Technical Debt

| Icon theming | Non-image items need proper icons |
| Error fallbacks | Scanner/Provider graceful degradation |
| Unit tests | None yet |
| Aspect cache | Read dimensions before layout |

---

## 🏗️ Backend Core Overhaul (From Audit)

### Active GitHub Issues (v0.5.0)
- [x] **Sorting Logic** (#6) - Implemented in `core/sorter.py`
- [x] **Async Thumbnails** (#7) - Implemented via `QQuickAsyncImageProvider`
- [ ] **UI Error Feedback** (#8) - Visual alerts for failures (partial skips)

### Critical Infrastructure
- [ ] **Job System Refactor** (`file_operations.py`)
    - [ ] Create `Job` class (UUID, progress tracking)
    - [ ] Create `JobManager` (Queueing, Global Progress)
    - [ ] Convert `FileOperations` to use Jobs (enables batching)
- [ ] **Parallelize File Ops (FLAW-003):** Refactor `FileOperations.py` to support multiple concurrent operations (e.g., copy + delete simultaneously).
- [ ] **Address Bar:**
- [x] **Search Engine Implementation (fd + Gio)**
    - **Status:** Core backend implemented in `core/search.py` and `core/search_worker.py`.
    - **Architecture:**
        - **Primary Engine (`fd`/`fdfind`):** Rust-based, 10-50x faster than `os.walk`. Returns paths via subprocess streaming.
        - **Fallback Engine (`os.scandir`):** Pure Python, works on Android/Termux when `fd` unavailable.
        - **Metadata Hydration:** Gio `query_info()` fetches size/date/icon lazily (only for visible items).
        - **Integration:** `AppBridge.startSearch()` / `cancelSearch()` slots wired to QML.
    - **Remaining:**
        - [ ] QML Search Bar UI component
        - [ ] Progressive loading (Phase 1: names, Phase 2: metadata, Phase 3: thumbnails)
- [ ] **Search Backend Testing (Pending)**
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
- [ ] **Trash Management**
    - [ ] Implement `restoreFile()` logic
    - [ ] Implement `emptyTrash()`

### Missing Core Stubs
- [ ] `core/file_properties.py` (Properties Dialog backend)
- [x] `core/search.py` (Implemented: FdSearchEngine, ScandirSearchEngine, SearchWorker)
- [ ] `core/shortcuts.py` (Centralized keybinds)
- [ ] `core/undo_manager.py` (Depends on Job System)

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
- [ ] Undo/Redo for file operations
- [ ] Search within folder

---

## Notes

```python
# Open With helper (for future context menu)
from gi.repository import Gio

def get_apps_for_file(path: str) -> list[dict]:
    file = Gio.File.new_for_path(path)
    info = file.query_info("standard::content-type", Gio.FileQueryInfoFlags.NONE)
    apps = Gio.AppInfo.get_all_for_type(info.get_content_type())
    return [{"name": a.get_name(), "app_info": a} for a in apps]
```

Benefits of the Current Approach
Benefit	Explanation
True Masonry Layout	Each item has its own height based on aspect ratio — visually appealing, like Pinterest.
Reactive Zoom	Changing columnWidth instantly updates all items — no manual refresh needed.
Simple Code	Everything is declarative QML — no complex imperative logic.
Fallbacks	Handles loading states (placeholder), missing dimensions, and directories gracefully.
Can We Offload Calculations to Python/Rust/Go?
Short answer: Not easily, and it wouldn't help much.

Here's why:

Approach	Feasibility	Why It Doesn't Help
Python	✅ Possible	Python is slower than QML's JavaScript. The binding recalculation happens in Qt's C++ engine; moving it to Python would add IPC overhead and be slower.
Rust/Go	⚠️ Complex	Requires FFI bindings to Qt. Even if you compute heights in Rust, you still need to pass them back to QML and trigger a model update — same layout churn.
C++ (QML Plugin)	✅ Best Option	You can write a C++ helper that computes all heights once and exposes them as a role in the model. But this is significant effort.
The Real Fix: Avoid Per-Delegate Bindings
The issue isn't where the calculation happens — it's how often it runs. The current approach recalculates imgHeight for every delegate on every resize.

Cython vs PyO3 for QML Integration

Aspect	Cython	PyO3 (Rust)
Language	Python-like (.pyx)	Rust
Learning Curve	Low (if you know Python)	Higher (new language)
Speedup	10-100x for numeric code	100-1000x (true native)
Qt Integration	❌ No native Qt bindings	⚠️ Possible via cxx-qt (experimental)
PySide6 Compatibility	✅ Seamless (same runtime)	⚠️ Tricky (need to pass data across FFI)
Build Complexity	Low (cythonize in setup.py)	Medium (need Rust toolchain + maturin)
Memory Safety	Python's GC	Rust's ownership (no GC)

Better Strategies:

Pre-compute aspect ratios in Python:
In FileScanner, calculate height / width once and store it as aspectRatio in the model.
QML just does: height: model.aspectRatio * width (one multiplication, no conditionals).
Debounce column width changes:
Instead of instantly updating columnWidth, use a Timer to delay the update until resize stops.
Use cacheBuffer on ListView:
Qt's ListView can pre-render items outside the viewport (cacheBuffer: 100). This reduces pop-in but doesn't fix resize jitter.
Recommendation: Pre-compute aspectRatio in Python (option 1). It's the cleanest fix with minimal code changes.