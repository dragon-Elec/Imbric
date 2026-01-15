# Imbric - Project Structure

> **Version:** 0.2.0-alpha  
> **Last Updated:** 2026-01-15  
> **Status:** Phase 2 Complete, Phase 3 In Progress

---

## Architecture Overview (Hybrid Stack)

```
┌─────────────────────────────────────────────────────────────────┐
│              IMBRIC (Qt Widgets Shell)                          │
│                                                                 │
│  ┌──────────────────────┐    ┌───────────────────────────────┐  │
│  │ MainWindow (Widgets) │◀─▶ │   QQuickView (Native Window)  │  │
│  │ - Toolbar            │    │   ┌────────────────────────┐  │  │
│  │ - Sidebar (Tree)     │    │   │      QML (Grid)        │  │  │
│  └──────────┬───────────┘    │   └────────────────────────┘  │  │
│             │                └───────────────────────────────┘  │
│             │                                                   │
│             ▼                                                   │
│   ┌────────────────────┐      ┌───────────────────────────┐     │
│   │   Core Logic       │◀────▶│     Bridge / Models       │     │
│   └────────────────────┘      └───────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Tree

```
imbric/
├── main.py                     # Entry point. Initializes QApplication.
├── requirements.txt            # Python deps
├── LICENSE                     
├── README.md                   
│
├── core/                       # Backend Logic (Python)
│   ├── gio_bridge/             
│   │   ├── bookmarks.py        
│   │   ├── volumes.py          
│   │   └── scanner.py          
│   └── image_providers/       
│       └── thumbnail_provider.py 
│
├── ui/                         # User Interface
│   ├── main_window.py          # [NEW] Hybrid Shell (Qt Widgets)
│   ├── models/                 
│   │   ├── sidebar_model.py    
│   │   └── column_splitter.py  
│   └── qml/
│       ├── views/
│       │   └── MasonryView.qml # Embedded Photo Grid
│       └── components/         # (Archived)
│
├── assets/                     # Template files only
│
└── docs/
    ├── ai-project-context/     # Project context documentation
    ├── archive/                # Legacy QML Shell files
    ├── structure.md            
    └── todo.md                 
```

---

## Module Specifications

### `ui/main_window.py` (New Shell)
| Class        | Type           | Responsibility |
| ------------ | -------------- | -------------- |
| `MainWindow` | `QMainWindow`  | Native window shell. Hosting QToolBar, QTreeView, QQuickView. |

---

### `ui/qml/` (Embedded Views)
| File                     | Type               | Responsibility |
| ------------------------ | ------------------ | -------------- |
| `views/MasonryView.qml`  | `QQuickItem`       | High-performance photo grid. Embedded in MainWindow via QWidget.createWindowContainer. |

---

## Data Flow (Updated)

```
User clicks QWidget Sidebar (QTreeView)
        │
        ▼
┌─────────────────────────┐
│   MainWindow (Python)   │  Calls self.navigate_to(path)
└───────────┬─────────────┘
            ├──────────────────────┐
            ▼                      ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│   Native Toolbar        │   │   update_scanner()       │
│   (Update Path Text)    │   │   (Clear/Scan Logic)     │
└─────────────────────────┘   └────────────┬─────────────┘
                                           │
                                           ▼
                                    FileScanner -> Splitter -> Models
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ QQuickView       │
                                  │ (MasonryView)    │
                                  └──────────────────┘
```

