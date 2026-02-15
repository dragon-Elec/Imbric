# QML Delegate Extraction Guide (Qt 6 / PySide6)

> **Purpose:** Extract inline delegates from nested Views into separate `.qml` files.
> **Updated:** 2026-02-02 | **Status:** Research Complete

---

## Executive Summary

Extracting a delegate from a nested `Repeater → ListView` structure into an external file **breaks implicit context propagation**. This is **by design** in Qt 6—external components are encapsulated and don't inherit the instantiation site's scope.

**The Solution:** Explicit Property Injection is the canonical Qt 6 pattern. The "boilerplate" is actually:
1. **Faster** (compile-time bindings vs runtime lookups)
2. **Safer** (validated by `qmllint`)
3. **Required** for `qmlcachegen` optimizations

---

## Table of Contents

1. [Why Inline Works, External Fails](#1-why-inline-works-external-fails)
2. [The FINAL Property Conflict](#2-the-final-property-conflict)
3. [PySide6 Backend Requirements](#3-pyside6-backend-requirements)
4. [The Three Dependency Types](#4-the-three-dependency-types)
5. [Implementation Templates](#5-implementation-templates)
6. [Performance Analysis](#6-performance-analysis)
7. [Common Pitfalls & Fixes](#7-common-pitfalls--fixes)
8. [Verification Checklist](#8-verification-checklist)

---

## 1. Why Inline Works, External Fails

### The Context Chain (Inline Delegates)

When a delegate is defined **inline**, the QML engine maintains an unbroken context hierarchy:

```
Root Context (appBridge, etc.)
  └── Repeater Context (modelData = column)
        └── ListView Context (model roles: path, name, isDir...)
              └── Delegate Item (can "see" everything above)
```

The delegate sits at the bottom of a "deep well" of `QQmlContext` objects. It can resolve:
- `model.path` → Injected by ListView
- `root.columnWidth` → ID scope lookup
- `appBridge` → Root context

### The Encapsulation Break (External Files)

When the delegate moves to `FileDelegate.qml`:

```
FileDelegate.qml (NEW isolated root context)
  └── Item { text: path }  // ❌ 'path' not defined here!
```

**The external file is an encapsulated type.** It does not inherit the lexical scope of where it's instantiated. This is a fundamental principle of component encapsulation—a component should not depend on the specific IDs of its container.

### The `modelData` vs `model` Confusion

| Keyword | Context | What It Means |
|:--------|:--------|:--------------|
| `model` | Inside ListView delegate | Current row's role accessor |
| `modelData` | Inside Repeater delegate | The current item from Repeater's model |
| `model.index` | Inside ListView delegate | Row index (also available as `index`) |

In our nested structure:
- **Outer Repeater:** `modelData` = One `SimpleListModel` (Python)
- **Inner ListView:** `model.path` = The `path` role from that `SimpleListModel`

---

## 2. The FINAL Property Conflict

### The Problem

`QQuickItem` (base class of `Item`, `Rectangle`, etc.) defines `width` and `height` as C++ properties with `FINAL` modifier.

```qml
// ❌ ERROR: Cannot override FINAL property
required property int width
required property int height
```

### The Solution

**Rename the model roles** in Python to avoid collision:

```python
# ❌ Bad: Collides with Item.width
WidthRole: b"width"

# ✅ Good: No collision
WidthRole: b"modelWidth"
HeightRole: b"modelHeight"
```

Then in QML:
```qml
required property int modelWidth
required property int modelHeight

// Use them for layout
height: modelHeight > 0 ? (modelHeight / modelWidth) * width : width
```

---

## 3. PySide6 Backend Requirements

### Critical: Use Byte Strings in `roleNames()`

The PySide6 bindings require explicit byte literals for role names:

```python
class SimpleListModel(QAbstractListModel):
    PathRole = Qt.UserRole + 1
    NameRole = Qt.UserRole + 2
    IsDirRole = Qt.UserRole + 3
    IconNameRole = Qt.UserRole + 4
    IsVisualRole = Qt.UserRole + 5
    WidthRole = Qt.UserRole + 6
    HeightRole = Qt.UserRole + 7

    def roleNames(self):
        # ✅ CRITICAL: Use bytes literals (b"...")
        return {
            self.PathRole: b"path",
            self.NameRole: b"name",
            self.IsDirRole: b"isDir",
            self.IconNameRole: b"iconName",
            self.IsVisualRole: b"isVisual",
            self.WidthRole: b"modelWidth",    # Renamed!
            self.HeightRole: b"modelHeight",  # Renamed!
        }
```

**If you use plain strings (`"path"` instead of `b"path"`), role injection may silently fail, causing `undefined` in QML.**

### Debug Verification

Add this to verify roles are working:

```python
# In Python, after model is populated
print(f"Role names: {model.roleNames()}")
print(f"Row count: {model.rowCount()}")
if model.rowCount() > 0:
    idx = model.index(0, 0)
    print(f"First item path: {model.data(idx, SimpleListModel.PathRole)}")
```

---

## 4. The Three Dependency Types

### Summary Table

| Dependency Type | Example | Pattern | Boilerplate |
|:----------------|:--------|:--------|:------------|
| **Model Roles** | `path`, `name`, `isDir` | `required property` | Auto-injected |
| **View Layout** | `columnWidth` | `property` + explicit bind | 1 line each |
| **App Services** | `appBridge`, `selectionModel` | **Singleton** (recommended) | 0 lines |

### 4.1 Model Roles (Auto-Injected)

If you declare a `required property` with a name matching a model role, Qt 6 auto-binds it:

```qml
// FileDelegate.qml
Item {
    required property string path      // ← Auto-bound to model.path
    required property string name      // ← Auto-bound to model.name
    required property bool isDir       // ← Auto-bound to model.isDir
    required property int index        // ← Auto-bound to row index
}
```

**No explicit binding needed in the parent!** The ListView handles injection.

### 4.2 View Layout (Explicit Binding)

Properties that come from the view structure (not the model) must be passed explicitly:

```qml
// FileDelegate.qml
Item {
    property real columnWidth: 200  // Default fallback
    
    width: columnWidth
}

// MasonryView.qml
delegate: FileDelegate {
    columnWidth: root.columnWidth  // ← Explicit binding
}
```

### 4.3 App Services (Singletons - Recommended)

For global services like `appBridge`, **register them as QML Singletons** to eliminate prop-drilling:

**Python Registration:**
```python
from PySide6.QtQml import qmlRegisterSingletonInstance

# In main.py, after creating the instances
qmlRegisterSingletonInstance("Imbric", 1, 0, "AppBridge", app_bridge)
qmlRegisterSingletonInstance("Imbric", 1, 0, "SelectionModel", selection_model)
```

**QML Usage:**
```qml
import Imbric

Item {
    MouseArea {
        onClicked: AppBridge.handleSelection(path)  // ← Direct access!
    }
}
```

**Benefits:**
- Zero boilerplate for service access
- Available in any component
- Type-safe (unlike context properties)

---

## 5. Implementation Templates

### 5.1 The Extracted Delegate (`FileDelegate.qml`)

```qml
import QtQuick
import QtQuick.Controls

Item {
    id: delegateRoot

    // =========================================================================
    // 1. MODEL DATA CONTRACT (Auto-injected by ListView)
    // =========================================================================
    required property string path
    required property string name
    required property bool isDir
    required property bool isVisual
    required property string iconName
    required property int modelWidth   // Renamed from 'width'
    required property int modelHeight  // Renamed from 'height'
    required property int index

    // =========================================================================
    // 2. VIEW LAYOUT CONTRACT (Must be passed explicitly)
    // =========================================================================
    property real columnWidth: 200

    // =========================================================================
    // 3. STATE PROPS (Optional, for rename/cut styling)
    // =========================================================================
    property string renamingPath: ""
    property var cutPaths: []

    // =========================================================================
    // 4. COMPUTED PROPERTIES
    // =========================================================================
    width: columnWidth

    readonly property real imgHeight: {
        if (isDir) return width * 0.8
        if (modelWidth > 0 && modelHeight > 0)
            return (modelHeight / modelWidth) * width
        return width  // Square fallback
    }

    readonly property int footerHeight: 36
    height: imgHeight + footerHeight

    // Selection state (access via Singleton or passed prop)
    readonly property bool selected: {
        // If using Singleton:
        // return SelectionModel.isSelected(path)
        // If using prop:
        return false  // Placeholder
    }

    // =========================================================================
    // 5. VISUAL IMPLEMENTATION
    // =========================================================================
    Rectangle {
        anchors.fill: parent
        anchors.margins: 4
        radius: 4

        color: delegateRoot.selected ? palette.highlight : "transparent"
        opacity: cutPaths.indexOf(path) >= 0 ? 0.5 : 1.0

        // Thumbnail
        Image {
            id: img
            visible: isVisual
            // ... thumbnail logic
            source: isVisual ? "image://thumbnail/" + path : ""
        }

        // Theme Icon
        Image {
            visible: !isVisual
            source: !isVisual ? "image://theme/" + iconName : ""
        }

        // Footer with name
        Text {
            text: name
            visible: renamingPath !== path
            // ... styling
        }
    }

    // =========================================================================
    // 6. INTERACTION (Use Singletons for clean access)
    // =========================================================================
    // DragHandler, DropArea, etc. can use AppBridge directly if registered
}
```

### 5.2 The Parent View (`MasonryView.qml`)

```qml
import QtQuick
import "components" as Components

Item {
    id: root
    property real columnWidth: appBridge ? appBridge.targetCellWidth : 250
    property string pathBeingRenamed: ""

    Repeater {
        model: columnModels

        delegate: ListView {
            id: columnListView
            width: root.columnWidth
            height: contentHeight
            interactive: false
            model: modelData  // ← The SimpleListModel for this column

            delegate: Components.FileDelegate {
                // ─────────────────────────────────────────────────────────────
                // Model roles: AUTO-INJECTED (no binding needed!)
                // path, name, isDir, isVisual, iconName, modelWidth, 
                // modelHeight, index are all automatically bound.
                // ─────────────────────────────────────────────────────────────

                // ─────────────────────────────────────────────────────────────
                // View Layout: EXPLICIT BINDING
                // ─────────────────────────────────────────────────────────────
                columnWidth: root.columnWidth

                // ─────────────────────────────────────────────────────────────
                // State Props: EXPLICIT BINDING
                // ─────────────────────────────────────────────────────────────
                renamingPath: root.pathBeingRenamed
                cutPaths: AppBridge.cutPaths ?? []  // Singleton access
            }
        }
    }
}
```

### 5.3 Register in `qmldir`

```
// ui/qml/components/qmldir
module components
FileDelegate 1.0 FileDelegate.qml
SelectionModel 1.0 SelectionModel.qml
RenameField 1.0 RenameField.qml
RubberBand 1.0 RubberBand.qml
```

---

## 6. Performance Analysis

### Myth: "More Properties = Slower"

**Reality: Explicit properties are FASTER.**

| Pattern | Mechanism | Speed |
|:--------|:----------|:------|
| **Implicit Context** | Runtime hash-map lookup through context chain | Slower |
| **Required Property** | Compile-time binding, optimized by `qmlcachegen` | Faster |

### Why?

1. **Implicit:** When `text: path` is evaluated, the engine searches:
   - Is `path` on this object? No.
   - Is `path` in this context? No.
   - Is `path` in parent context? Yes!
   
   This lookup happens at **runtime**, repeatedly.

2. **Explicit:** When `required property string path` is declared:
   - `qmlcachegen` generates C++ code with a direct property setter.
   - The binding is established once at instantiation.
   - No runtime lookup.

### Binding Loop Prevention

Ensure unidirectional geometry flow:
```
View sets → Delegate.columnWidth
Delegate computes → Delegate.height (based on content)
View respects → Delegate.height (for layout)
```

**Never** have Delegate try to set View's dimensions.

---

## 7. Common Pitfalls & Fixes

| Pitfall | Symptom | Fix |
|:--------|:--------|:----|
| **Lost Model Context** | "Unable to assign [undefined]" | Use `required property` matching role names. Roles auto-inject. |
| **FINAL Property Error** | "Cannot override FINAL property" | Rename `width`→`modelWidth`, `height`→`modelHeight` in Python. |
| **Silent Role Failure** | `model.path` is `undefined` | Use byte strings in `roleNames()`: `b"path"` not `"path"`. |
| **Component Not Found** | "FileDelegate is not a type" | Add to `qmldir`: `FileDelegate 1.0 FileDelegate.qml` |
| **Broken Signals** | Click does nothing | Ensure `MouseArea` isn't blocked. Check `propagateComposedEvents`. |
| **Service Access Verbose** | 5+ lines to pass `appBridge` | Register as Singleton: `qmlRegisterSingletonInstance(...)` |
| **Binding Loop** | "Binding loop detected" | Ensure geometry flows View→Delegate, never reverse. |

---

## 8. Verification Checklist

### Pre-Flight (Python)
- [ ] `roleNames()` uses byte strings: `b"path"`, `b"name"`, etc.
- [ ] `width`/`height` roles renamed to `modelWidth`/`modelHeight`
- [ ] `AppBridge` registered as Singleton (optional but recommended)
- [ ] Model is printing correct data in console

### Component Definition (`FileDelegate.qml`)
- [ ] All model roles declared as `required property`
- [ ] No use of `required property int width` or `height`
- [ ] View-layout props use regular `property` with defaults
- [ ] No references to undefined IDs (`root`, `appBridge` without Singleton)

### Parent View (`MasonryView.qml`)
- [ ] Model roles NOT explicitly bound (auto-injection handles them)
- [ ] View-layout props explicitly bound (`columnWidth: root.columnWidth`)
- [ ] `qmldir` updated with `FileDelegate` entry

### Runtime Testing
- [ ] `console.log()` prints correct values in `Component.onCompleted`
- [ ] No "undefined" errors in console
- [ ] Thumbnails/icons render correctly
- [ ] Selection highlight works
- [ ] Double-click opens item
- [ ] Drag & Drop functional

---

## References

- Qt 6 Docs: [Required Properties](https://doc.qt.io/qt-6/qtqml-syntax-objectattributes.html#required-properties)
- Qt 6 Docs: [Defining QML Types from C++](https://doc.qt.io/qt-6/qtqml-cppintegration-definetypes.html)
- PySide6 Docs: [QAbstractListModel](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractListModel.html)
- KDE Developer: [Porting to Qt 6 / Required Properties](https://develop.kde.org/docs/getting-started/kirigami/)
