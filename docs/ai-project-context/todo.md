# Imbric TODO

> **Convention:** `[x]` done, `[/]` in progress, `[ ]` pending  
> **Bugs:** See `BUGS_AND_FLAWS.md`

---

## Active

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

| Item | Note |
|:-----|:-----|
| Icon theming | Non-image items need proper icons |
| Error fallbacks | Scanner/Provider graceful degradation |
| Unit tests | None yet |
| Aspect cache | Read dimensions before layout |

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