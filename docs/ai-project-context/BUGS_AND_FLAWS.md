# 🐞 Bug & Flaw Center

> **Purpose:** Centralized, chronological bug tracking with root-cause analysis.  
> **Philosophy:** Solve causes, not symptoms. Trace dependencies. Block random fixes.

---

## Maintenance Rules (CRITICAL)

1. **No Hardcoded Fixes.** Each bug entry has a `Resolution Path`, not a solution. The path specifies which files/modules to scan first to find the best approach.
2. **Dependency Chain.** Before fixing any bug, list what must be fixed first (if any).
3. **Same-Category Bugs.** If a bug relates to an existing entry, add to that entry (don't duplicate).
4. **Root Cause.** Always document **why** the bug exists, not just **what** it does.
5. **Verification.** Mark `FIXED` only after user confirms. Use `IMPLEMENTED` otherwise.

---

## Resolution Strategy (Priority Order)

```
1. Backend Integrity (data safety, silent failures)
2. Layout Stability (visual order, scrolling)
3. Interaction (responsiveness, focus)
4. Polish (visual glitches, edge cases)
```

---

## 🔴 Backend Integrity

### ✅ BUG-001: FileOps Silent Fail

[file_operations.py](cci:7://file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py:0:0-0:0) | CRIT | Fixed 2026-01-21
Was: Recursive ops abort on 1st error, no aggregate. 
Fix: `_skipped_files[]` accumulator, `finished.emit(..., "dest|PARTIAL:N")` in signal

---

## ✅ Verified Working (No Code Change Needed)

### BUG-005: Dir-Over-Dir Paste Failure

[file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | MEDIUM | Verified 2026-01-22
Was: Concern that pasting directory over existing directory may fail silently.
Status: **Already working correctly** - `_recursive_move_merge()` properly handles WOULD_MERGE errors.
Note: Dialog shows "Overwrite" button which is confusing for folders. Future enhancement: Add explicit "Merge folders" option.

---

## 💤 Dormant / Platform Specific

### BUG-004: `AppBridge` Blocking Drag

[app_bridge.py](file:///home/ray/Desktop/files/wrk/Imbric/ui/models/app_bridge.py) | MEDIUM (Win Only) | Low Priority
Was: `drag.exec()` blocks event loop on Windows.
Why: Qt design behavior. Non-blocking on Linux/macOS.
Path: Ignore for Linux. Use QTimer/Thread for Windows.

---

## 🟢 Polish & Edge Cases

### BUG-006: F2 Inline Rename Focus Loss

[MasonryView.qml](file:///home/ray/Desktop/files/wrk/Imbric/ui/qml/views/MasonryView.qml) | LOW (Qt Quirk) | OPEN
Was: F2 rename field loses focus immediately (~1/15 times).
Why: QML `Loader` emits transient `activeFocusChanged=false`. Hard to fix.
Path: 1. Monitor Qt updates. 2. Scan Qt forums for Loader solutions.

---

### BUG-007: Rubberband Selection Ignores Sort Order

**Files:** [selection_helper.py](file:///home/ray/Desktop/files/wrk/Imbric/core/selection_helper.py), [column_splitter.py](file:///home/ray/Desktop/files/wrk/Imbric/ui/models/column_splitter.py)  
**Severity:** MEDIUM | **Status:** OPEN

**Symptom:**  
Rubberband (marquee) selection highlights wrong items when sorting is enabled. The visual selection rectangle selects items based on their original filesystem order, not the displayed sorted order.

**Root Cause Analysis:**

1. **Display uses sorted data:**  
   `ColumnSplitter._redistribute()` calls `self._sorter.sort(self._all_items)` before dealing to column models. QML sees sorted items. ✅

2. **SelectionHelper uses unsorted data:**  
   ```python
   # selection_helper.py:23
   items = splitter.getAllItems()
   ```
   
   ```python
   # column_splitter.py:200-205
   def getAllItems(self) -> list[dict]:
       return self._all_items  # ← Returns RAW unsorted list!
   ```

3. **Geometry mismatch:**  
   SelectionHelper iterates `items` and calculates `col_idx = i % col_count`. This assumes items are in the same order as the display, but they're not.

**Investigation Required:**
- Review [selection_helper.py:35-37](file:///home/ray/Desktop/files/wrk/Imbric/core/selection_helper.py#L35-L37) — iteration logic
- Review [column_splitter.py:162-178](file:///home/ray/Desktop/files/wrk/Imbric/ui/models/column_splitter.py#L162-L178) — `_redistribute()` sorting
- Consider whether `getAllItems()` should return sorted or add `getSortedItems()`

**Proposed Fix:**
Add `getSortedItems()` method to `ColumnSplitter` that returns `self._sorter.sort(self._all_items)`. Update `SelectionHelper` to use this instead.



---

## ✅ Resolved

*(Move entries here when user confirms fix)*

- BUG-001: FileOps Silent Fail
- BUG-002: FileScanner Sync I/O in Async Loop
- BUG-005: Dir-Over-Dir Paste (verified working, no code change needed)
### ✅ BUG-008: Symlink Thumbnail Failure

Files: [thumbnail_provider.py](file:///home/ray/Desktop/files/wrk/Imbric/core/image_providers/thumbnail_provider.py)  
Severity: LOW | Status: FIXED (2026-01-23)

Symptom:
Log error: `QML QQuickImage: Failed to get image from provider: image://thumbnail//.../Link to data copy`.
Thumbnails for symlinks (or copies of symlinks) fail to generate or load, showing a broken image or empty space.

Root Cause Analysis:
1. `ThumbnailProvider` may not be dereferencing symlinks correctly before passing path to `common_factory.lookup/save`.
2. GNOME Thumbnail Factory expects a canonical URI/path.
3. If the symlink points to a directory or a non-image, the provider might be trying to thumb the link itself instead of the target owner or falling back to a mime-type icon.

Investigation Required:
- Check `thumbnail_provider.py` requestImage method.
- Does it use `os.path.realpath(path)`?
- Verify if `GnomeDesktop.DesktopThumbnailFactory` handles symlinks automatically or needs manual dereference.

Proposed Fix:
Ensure `path` is resolved to absolute target path before requesting thumbnail, OR handle `GLib.Error` gracefully and fallback to generic icon.
### ✅ FLAW-003: Sequential File Operations (Single Worker Thread)

Files: [file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py)  
Severity: MEDIUM | Status: **FIXED (2026-01-24)**

Symptom:
Initiating a long-running operation (e.g., copying 10GB) blocks subsequent operations (e.g., trashing a file) until the first one completes.

Root Cause:
`FileOperations` used a single `QThread` and `_FileOperationWorker`. Signals were processed sequentially.

Fix Applied:
Refactored to QThreadPool + QRunnable pattern:
- `CopyRunnable`, `MoveRunnable`, `TrashRunnable`, `RenameRunnable`, `CreateFolderRunnable`
- Each operation runs as independent QRunnable with its own `Gio.Cancellable`
- Added `FileJob` dataclass for per-operation tracking (UUID, status)
- Per-operation cancellation supported via `cancel(job_id)`
- Signals updated to include `job_id` for tracking
