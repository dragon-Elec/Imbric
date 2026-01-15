```
╔═════════════════════════════════════════════════════════════╗
║                                                             ║
║        ██╗ ███╗   ███╗ ██████╗  ██████╗  ██╗  ██████╗       ║
║        ██║ ████╗ ████║ ██╔══██╗ ██╔══██╗ ██║ ██╔════╝       ║
║        ██║ ██╔████╔██║ ██████╔╝ ██████╔╝ ██║ ██║            ║
║        ██║ ██║╚██╔╝██║ ██╔══██╗ ██╔══██╗ ██║ ██║            ║
║        ██║ ██║ ╚═╝ ██║ ██████╔╝ ██║  ██║ ██║ ╚██████╗       ║
║        ╚═╝ ╚═╝     ╚═╝ ╚═════╝  ╚═╝  ╚═╝ ╚═╝  ╚═════╝       ║
║                                                             ║
║           Your Photos. Your Filesystem. Zero Lag.           ║
║                                                             ║
╚═════════════════════════════════════════════════════════════╝
```

<br/>

> **Imbric** doesn't manage your files.  
> It *lenses* them.

<br/>

---

<br/>

## The Philosophy

Most file managers treat photos like spreadsheet rows.  
Imbric treats them like **what they are**: visual objects with shape, color, and time.

```
┌───────────────────────────────────────────────────────────────┐
│                             vs.                               │
│   Traditional Grid                    Imbric Masonry          │
│                              │                                │
│   ┌────┐ ┌────┐ ┌────┐       │    ┌────────┐ ┌────┐┌──┐       │
│   │    │ │    │ │    │       │    │        │ │    ││  │       │
│   │    │ │    │ │    │       │    │        │ ├────┤│  │       │
│   └────┘ └────┘ └────┘       │    │        │ │    ││  │       │
│   ┌────┐ ┌────┐ ┌────┐       │    └────────┘ │    ││  │       │
│   │    │ │    │ │    │       │    ┌────────┐ └────┘└──┘       │
│   └────┘ └────┘ └────┘       │    │        │ ┌────────┐       │
│                              │    └────────┘ │        │       │
│   Wasted space. ❌           │                                │
│                              │    Every pixel used. ✓         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

<br/>

---

<br/>

## How It Works

Imbric is a **lens**, not an engine.

It doesn't reinvent Linux. It *uses* it.

| What           | How Imbric Does It              | Why It's Fast                        |
| -------------- | ------------------------------- | ------------------------------------ |
| **Thumbnails** | `GnomeDesktop.ThumbnailFactory` | Same cache as Nautilus. Pre-baked.   |
| **File Ops**   | `Gio` (GLib I/O)                | Kernel-level. Zero Python overhead.  |
| **Layout**     | Split-Column "Card Dealing"     | Qt's C++ engine. Not JS. Not Python. |
| **Sorting**    | `QSortFilterProxyModel`         | C++ side. Instant.                   |

```
                    ┌──────────────────┐
                    │   YOUR PHOTOS    │
                    └────────┬─────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  LinuxDesktop + Gio (C libs) │  ◀── The heavy lifting
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Python (Thin Orchestrator)  │  ◀── Just glue code
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Qt Quick / QML (60fps UI)   │  ◀── What you see
              └──────────────────────────────┘
```

<br/>

---

<br/>

## Get It Running

```bash
# Prerequisites (Debian/Ubuntu/Zorin)
sudo apt install python3-gi gir1.2-gnomedesktop-3.0

# Clone & Run
git clone https://github.com/yourusername/imbric.git
cd imbric
pip install -r requirements.txt
python3 main.py ~/Pictures
```

<br/>

---

<br/>

## Roadmap

```
Phase 1 ███████████████████████████████████████░░░░░░░░  [DONE]  Native Shell
Phase 2 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  [NEXT]  Masonry Engine
Phase 3 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  [    ]  Thumbnails
Phase 4 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  [    ]  Polish
```

<br/>

---

<br/>

## License

MIT. Use it. Fork it. Ship it.  
See [LICENSE](LICENSE).

<br/>

---

<br/>

```
Built for Linux. Built with GNOME and QT. Built to be fast.
```
