# Imbric: Active Tasks

> **Last Updated:** 2026-01-15  
> **Current Phase:** Phase 3 — Thumbnail Integration (Bug Fixing)

---

## Current Focus

**Active Task:** Fix Folder Display Bug

**Context:** MasonryView works but folders show as blank boxes. Need to either show folder icons OR add navigation so clicking folders opens them.

**Blockers:** None — ready to fix.

---

## Known Bugs 🐛

| ID | Summary | Priority | File |
|----|---------|----------|------|
| #001 | Folder boxes blank (no icon) | P1 | `thumbnail_provider.py` |
| #002 | Click folder does nothing | P1 | `MasonryView.qml` |
| #003 | Image heights randomized | P2 | `MasonryView.qml` |

---

## Task Backlog

### 🟠 High Priority (P1)

- [x] Fix #001: Return folder icon from ThumbnailProvider
- [x] Fix #002: Click traversal for folders
- [x] Fix #003: True Aspect Ratios
- [x] Fix #004: MasonryView layout width fix

## Backlog (Low Priority)
- [ ] File Preview (Fullscreen)
- [ ] Keyboard Navigation
- [ ] Sorting Logic
- [ ] Fix #002: Add MouseArea to MasonryView delegate
- [ ] Add Breadcrumb/Back navigation

### 🟡 Medium Priority (P2)

- [ ] Fix #003: Read actual image dimensions for heights
- [ ] Async thumbnail generation (background thread)
- [ ] Sorting logic (QSortFilterProxyModel)

---

## Recently Completed

- [x] Phase 1: Native Shell
- [x] Phase 2: Split-Column Engine (Scanner, Splitter, MasonryView)
- [x] Phase 3: ThumbnailProvider (GnomeDesktop integration)
- [x] Sidebar navigation → appBridge connection
