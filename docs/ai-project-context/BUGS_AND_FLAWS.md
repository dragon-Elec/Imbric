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

### ✅ BUG-002: `FileScanner` Sync I/O in Async Loop

[scanner.py](file:///home/ray/Desktop/files/wrk/Imbric/core/gio_bridge/scanner.py) | HIGH | Fixed 2026-01-22
Was: `os.path.join` (syscall) inside async callback causing micro-stutters.
Fix: Replaced with string concatenation in `_on_files_retrieved()`.

---

## 🟡 Interaction & Responsiveness

### BUG-004: `AppBridge` Blocking Drag

- **Severity:** MEDIUM (Responsiveness)
- **Location:** `ui/models/app_bridge.py` → `startDrag()`
- **What:** `drag.exec()` blocks main thread. Icon pixmap generated sync.
- **Why:** Standard Qt DnD pattern; pixmap generation overlooked.
- **Impact:** UI freezes during drag until drop completes.
- **Depends On:** None.
- **Resolution Path:**
  
  1. Scan Qt docs for async drag patterns.
  
  2. Pre-cache drag pixmap on selection change.
  
  3. Consider `QTimer.singleShot(0, drag.exec)` deferral.

### BUG-005: Dir-Over-Dir Paste Failure

- **Severity:** MEDIUM (Data Safety)
- **Location:** `core/file_operations.py` → `do_move()`
- **What:** Pasting directory over existing same-name directory may fail silently.
- **Why:** `WOULD_MERGE` error handler exists but may not cover all cases.
- **Impact:** User expects merge dialog; gets error or nothing.
- **Depends On:** `BUG-001` (error aggregation needed for proper reporting).
- **Resolution Path:**
  
  1. Reproduce: Create `A/x.txt`, `B/A/y.txt`, cut A from root, paste into B.
  
  2. Scan `_recursive_move_merge()` for edge cases.
  
  3. Scan `ConflictResolver` for missing "Merge" vs "Replace" option.

---

## 🟢 Polish & Edge Cases

### BUG-006: F2 Inline Rename Focus Loss

- **Severity:** LOW (Visual Glitch)
- **Location:** `ui/qml/views/MasonryView.qml` → Loader/TextArea
- **What:** ~1/15 times F2 rename field loses focus immediately.
- **Why:** QML `Loader` emits transient `activeFocusChanged=false` during component swap.
- **Impact:** Rename closes before user types.
- **Workaround Applied:** Removed `onActiveFocusChanged` auto-commit. Now Enter/Esc only.
- **Depends On:** None (QML framework quirk).
- **Resolution Path:**
  
  1. This is a Qt bug. Monitor Qt updates.
  
  2. If revisited: Scan Qt forums for `Loader` focus solutions.

---

## ✅ Resolved

*(Move entries here when user confirms fix)*

- BUG-001: FileOps Silent Fail
- BUG-002: FileScanner Sync I/O in Async Loop