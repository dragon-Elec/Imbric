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
6. **Chronological Focus.** Always prioritize the *Resolve Dependencies* chain (see Section 2.1) over random fixes. Stability > Features.

---

## Resolution Strategy (Priority Order)

```
1. Backend Integrity (data safety, silent failures)
2. Layout Stability (visual order, scrolling)
3. Interaction (responsiveness, focus)
4. Polish (visual glitches, edge cases)
```

## 🔗 Chronological Resolution Path (Dependency Chain)

This section outlines the optimal order for fixing active bugs. Fixing these in order prevents regressions and simplifies subsequent fixes.

### Phase 1: Foundation (Stability & Data Integrity)

1.  **[BUG-012: Race Condition in "New Folder"](./BUGS_AND_FLAWS.md#bug-012)**
    *   **Status:** FIXED (2026-01-30)
    *   **Why First:** Prevents phantom file operations and race conditions in `AppBridge`.
    *   **Unlocks:** Reliable transaction recording for folder creation (BUG-023).

2.  **[BUG-023: Missing Transactions (Rename/New Folder)](./BUGS_AND_FLAWS.md#bug-023)**
    *   **Why Second:** Ensures *every* file operation (even simple ones like Rename) has a Transaction ID for Undo history.
    *   **Unlocks:** Complete Undo/Redo coverage (currently fails for renames).

3.  **[FLAW-004: Incomplete Undo Atomicity](./BUGS_AND_FLAWS.md#flaw-004)**
    *   **Why Third:** Now that we have transactions for everything (Step 2), we must ensure they roll back cleanly even if partially failed.
    *   **Unlocks:** Bulletproof Undo/Redo system.

### Phase 2: User Experience (Feedback)

4.  **[BUG-016: Search Blindness](./BUGS_AND_FLAWS.md#bug-016)**
    *   **Why Last:** Pure UI feedback issue. Doesn't risk data integrity.
    *   **Dependency:** None (independent), but lower priority than data safety.

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



---



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

### ✅ BUG-011: Incomplete Undo Stack
[core/undo_manager.py](file:///home/ray/Desktop/files/wrk/Imbric/core/undo_manager.py) | MEDIUM | FIXED (2026-01-26)
Was: Trash/Restore/Mkdir undo missing. Async race conditions.
Why: `_execute` returned optimistic success before I/O completion.
Path: Rewrote UndoManager to be event-driven (async-aware). Added `TransactionManager` wiring.

### ✅ BUG-019: Missing UI Init
[ui/__init__.py](file:///home/ray/Desktop/files/wrk/Imbric/ui/__init__.py) | HIGH | FIXED (2026-01-27)
Was: ModuleNotFoundError when importing from `ui`.
Why: Missing `__init__.py` preventing package discovery.
Path: Added empty `__init__.py`.

### ✅ BUG-020: Transaction Logic Missing
[core/transaction_manager.py](file:///home/ray/Desktop/files/wrk/Imbric/core/transaction_manager.py) | CRITICAL | FIXED (2026-01-27)
Was: `TransactionManager` ignored start/finish signals (empty methods) and crashed on Conflict Resolution (`NameError`).
Why: Logic was stubbed out/commented.
Path: Restored logic, fixed variable scope, verified with `test_transaction_conflict.py`.

### ✅ BUG-021: Silent Permission Failure
[core/file_workers.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_workers.py) | HIGH | FIXED (2026-01-27)
Was: `CreateFolderRunnable` ignored `PermissionError` and reported success (false positive).
Why: Swallow `GLib.Error` without emitting error signal.
Path: Patched `emit_finished` flow to separate error vs cancellation. Verified with `test_stress_scenarios.py`.

### ✅ BUG-022: Relative Path Undo Failure
[core/file_workers.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_workers.py) | MEDIUM | FIXED (2026-01-27)
Was: Undo Rename failed because worker returned relative path `renamed.txt`.
Why: `Gio` sometimes returns relative paths; `TransactionManager` needs absolute for Undo.
Path: Forced absolute path calculation in `RenameRunnable`. Verified with `test_undo_logic.py`.

### ✅ BUG-024: The One Job Issue (UI Jitter)
[core/file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | HIGH | FIXED (2026-02-01)
Was: Mult-file operations fired N separate signals, overloading UI and causing jitter.
Why: Loop-based implementation (`for path in paths: trash(path)`).
Path: Wrapped batch operations in a Transaction; `TransactionManager` now aggregates progress and emits 1 signal per batch update.

### ✅ BUG-025: Job System Refactor
[core/file_operations.py](file:///home/ray/Desktop/files/wrk/Imbric/core/file_operations.py) | HIGH | FIXED (2026-02-01)
Was: Blocking file operations and sequential queue.
Why: Legacy single-threaded architecture.
Path: Implemented `QThreadPool` + `FileJob` + `TransactionManager`. Logic fully migrated.

---

## 🆕 Unresolved Flaws (Jan 25 Analysis)

### 🔴 Critical (Data Integrity)


### ✅ BUG-010: Destructive Folder Overwrite
**Files:** `ui/elements/conflict_dialog.py` / `core/file_workers.py`
**Severity:** HIGH
**Status:** IMPLEMENTED (Backend) (2026-01-27)
**Symptom:** "Overwrite" action on a folder might replace the *entire* target folder structure instead of merging.
**Path:** Backend logic in `_recursive_merge` confirmed in `file_workers.py`.

### ✅ BUG-013: Event Flooding (Performance)
**Files:** `core/file_monitor.py`
**Severity:** HIGH
**Status:** IMPLEMENTED (2026-01-28)
**Symptom:** Pasting 5,000 files triggers flood of UI refreshes.
**Path:** Implemented signal coalescing in `FileMonitor`.

### ✅ BUG-014: Stale Metadata
**Files:** `core/file_monitor.py`
**Severity:** LOW
**Status:** IMPLEMENTED (2026-01-28)
**Symptom:** File sizes/dates do not update if changed externally.
**Path:** Enabled `CHANGED` event monitoring with throttling.



### ✅ BUG-012: Race Condition in "New Folder"
**Files:** `ui/models/app_bridge.py` / `core/file_workers.py`
**Severity:** MEDIUM
**Status:** FIXED (2026-01-30)
**Symptom:** Rapidly clicking "New Folder" can cause backend errors if the second click happens before the first folder is physically created.
**Path:** Implemented atomic "Try Create -> If Exists, Auto-Rename" loop in `CreateFolderRunnable`.

### 🟡 Performance & Events



### BUG-015: Blind Status Bar
**Files:** `ui/elements/status_bar.py`
**Severity:** LOW
**Symptom:** Shows "0 items" during long directory scans with no "Loading..." indicator.
**Path:** Add `onScanStarted` signal to `FileScanner` and connect to StatusBar to show a spinner or "Scanning..." text.

### 🔵 Interaction Limitations

### BUG-016: Search Blindness
**Files:** `core/search_worker.py`
**Severity:** low becase search bar is not impelemented
**Symptom:** No progress feedback during search. Long searches look like the app has hung.
**Path:** Emit periodic "progress" signals (e.g., "Scanned 1000 files...") or indefinite spinner state.



### BUG-018: Missing "Open Terminal"
**Files:** `ui/models/app_bridge.py`
**Severity:** LOW (Power User Feature)
**Symptom:** No ability to open a terminal in the current directory.
**Path:** Add context menu action. Use `Gio.AppInfo.launch_default_for_uri` with a terminal URI or `subprocess` to launch default terminal.

