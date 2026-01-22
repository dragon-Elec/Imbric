# Imbric TODO

> **Convention:** `[x]` done, `[/]` in progress, `[ ]` pending  
> **Bugs:** See `BUGS_AND_FLAWS.md`

---

## Active

- [ ] Sorting logic (`sorter.py` stub → impl)
- [ ] Async thumbnail generation (background thread)
- [ ] UI Error Feedback — `ProgressOverlay` show `PARTIAL:N` skipped files

---

## Backlog

- [ ] File Preview (Spacebar fullscreen)
- [ ] Keyboard Navigation (Arrow keys in grid)
- [ ] EXIF/Metadata Panel
- [ ] Symlink overlay icons
- [ ] Column-Major layout option (Pinterest-style, post-alpha)

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