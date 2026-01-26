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
[core/file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | CRITICAL | FIXED (2026-01-21)
Was: Recursive ops aborted on 1st error, no aggregate reporting.
Why: Exceptions halted execution immediately.
Path: Added `_skipped_files[]` accumulator and `PARTIAL:N` signal flag.

### 🔧 BUG-009: Silent Partial Failures (UI)
[ui/widgets/progress_overlay.py](file:///home/ray/Desktop/files/wrk/Imbric/ui/widgets/progress_overlay.py) | CRITICAL | IMPLEMENTED (2026-01-25)
Was: UI ignored `PARTIAL` signal, hiding progress bar on failure.
Why: `onOperationCompleted` ignored `result_data`.
Path: Added detection for `PARTIAL:` string, disabled auto-hide, and added warning state.

---

## ✅ Verified Working (No Code Change Needed)

### ✅ BUG-005: Dir-Over-Dir Paste Failure
[core/file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | MEDIUM | VERIFIED (2026-01-22)
Was: Suspected failure when pasting directory over existing one.
Why: Concern about `WOULD_MERGE` handling.
Path: Verified `_recursive_move_merge()` handles this correctly. (Future: Add "Merge" button).

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

### ✅ BUG-007: Rubberband Selection Ignores Sort Order
[ui/models/column_splitter.py](file:///home/ray/Desktop/files/wrk/Imbric/ui/models/column_splitter.py) | MEDIUM | FIXED (2026-01-25)
Was: Marquee selection highlighted wrong items when sorting enabled.
Why: Hit-testing used unsorted `_all_items` list while display was sorted.
Path: Create `_sorted_items` cache in `ColumnSplitter` and use it for `getAllItems()`.

## ✅ Resolved

*(Move entries here when user confirms fix)*

- BUG-001: FileOps Silent Fail
- BUG-002: FileScanner Sync I/O in Async Loop
- BUG-005: Dir-Over-Dir Paste (verified working, no code change needed)
### ✅ BUG-008: Symlink Thumbnail Failure
[core/image_providers/thumbnail_provider.py](file:///home/ray/Desktop/files/wrk/Imbric/core/image_providers/thumbnail_provider.py) | LOW | FIXED (2026-01-23)
Was: Thumbnails failed for symlinks ("Link to data copy" error).
Why: GNOME Thumbnail Factory requires canonical paths, not symlink paths.
Path: Resolved path via `os.path.realpath` before requesting thumbnail.
### ✅ FLAW-003: Sequential File Operations
[core/file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | MEDIUM | FIXED (2026-01-24)
Was: Long ops blocked short ops (sequential queue).
Why: Single `QThread` serialization.
Path: Refactored to `QThreadPool` + `QRunnable` for parallel execution.

---

## 🆕 Unresolved Flaws (Jan 25 Analysis)

### 🔴 Critical (Data Integrity)


### BUG-010: Destructive Folder Overwrite
**Files:** `ui/dialogs/conflict_dialog.py`
**Severity:** HIGH
**Symptom:** "Overwrite" action on a folder might replace the *entire* target folder structure instead of merging.
**Path:** `ConflictResolver` needs specific `WOULD_MERGE` handling or a "Merge" option separate from "Overwrite" for directories.

### ✅ BUG-011: Incomplete Undo Stack
[core/undo_manager.py](file:///home/ray/Desktop/files/wrk/Imbric/core/undo_manager.py) | MEDIUM | FIXED (2026-01-26)
Was: Trash/Restore/Mkdir undo missing. Async race conditions.
Why: `_execute` returned optimistic success before I/O completion.
Path: Rewrote UndoManager to be event-driven (async-aware). Added `TransactionManager` wiring.

### BUG-012: Race Condition in "New Folder"
**Files:** `ui/models/app_bridge.py`
**Severity:** MEDIUM
**Symptom:** Rapidly clicking "New Folder" can cause backend errors if the second click happens before the first folder is physically created.
**Path:** Add a "creating_folder" semaphore/flag in `AppBridge` to block subsequent requests until completion.

### 🟡 Performance & Events

### BUG-013: Event Flooding
**Files:** `core/file_monitor.py`
**Severity:** HIGH (Performance)
**Symptom:** Pasting 5,000 files triggers 5,000 individual UI refreshes, freezing the app.
**Path:** Implement "Event Coalescing" (debounce timer). Wait 100-200ms after an event before emitting `directoryChanged`.

### BUG-014: Stale Metadata
**Files:** `core/file_monitor.py`
**Severity:** LOW
**Symptom:** Explicitly ignores `Gio.FileMonitorEvent.CHANGED`. File sizes/dates do not update if changed externally (e.g. by a download).
**Path:** Enable `CHANGED` event handling but throttle it heavily to avoid spam.

### BUG-015: Blind Status Bar
**Files:** `ui/widgets/status_bar.py`
**Severity:** LOW
**Symptom:** Shows "0 items" during long directory scans with no "Loading..." indicator.
**Path:** Add `onScanStarted` signal to `FileScanner` and connect to StatusBar to show a spinner or "Scanning..." text.

### 🔵 Interaction Limitations

### BUG-016: Search Blindness
**Files:** `core/search_worker.py`
**Severity:** MEDIUM
**Symptom:** No progress feedback during search. Long searches look like the app has hung.
**Path:** Emit periodic "progress" signals (e.g., "Scanned 1000 files...") or indefinite spinner state.

### BUG-017: Focus Trap on Rename
**Files:** `ui/qml/views/MasonryView.qml`
**Severity:** MEDIUM
**Symptom:** F2 rename relies on brittle `activeFocus` changes, leading to dead keys.
**Path:** Centralize focus logic. Use `State` machine for "View Mode" vs "Edit Mode".

### BUG-018: Missing "Open Terminal"
**Files:** `ui/models/app_bridge.py`
**Severity:** LOW (Power User Feature)
**Symptom:** No ability to open a terminal in the current directory.
**Path:** Add context menu action. Use `Gio.AppInfo.launch_default_for_uri` with a terminal URI or `subprocess` to launch default terminal.

