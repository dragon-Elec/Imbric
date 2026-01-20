# Refactoring "God Object" Input to Autonomous Delegates

The goal is to decouple the global `rubberBandArea` ("God Object") from individual file interactions. This will solve focus stealing issues (Inline Rename), simplify drag-and-drop logic, and prepare the architecture for multi-pane/multi-window support.

## User Review Required

> [!IMPORTANT]
> **Architecture Change**: Input handling for files (Click, Drag, Context Menu) will move from the global overlay to the individual file delegates.
> - **Visual Impact**: None intended.
> - **Behavior Impact**: Clicking a file will feel more "solid". Inline rename focus issues should be resolved.
> - **Risk**: Drag and drop behavior (specifically system drag) needs robust verification to ensure no regressions.

## Proposed Changes

### UI Components (`ui/qml/`)

#### [NEW] [ui/qml/components/MasonryDelegate.qml](file:///home/ray/Desktop/files/wrk/Imbric/ui/qml/components/MasonryDelegate.qml)
Create a new standalone component to encapsulate all file-level interaction.
- **Root Element**: `Item` (width/height from model)
- **Visuals**: `Rectangle` (highlight), `Image` (thumbnail), `Loader` (Name/Rename).
- **Input Handling**: `MouseArea` (anchors.fill: parent).
  - `onClicked`:
    - `selectionModel.toggle(model.path, mouse.modifiers)`
    - `root.forceActiveFocus()` (Ensure focus shifts to this item)
  - `onDoubleClicked`: `appBridge.openPath(model.path)`
  - `onPressAndHold`: `appBridge.showContextMenu([model.path])`
  - `onRightClicked`:
    - If not selected: `selectionModel.select(model.path)`
    - `appBridge.showContextMenu(selectionModel.selection)`
  - **Drag Logic**:
    - `drag.target`: Internal interaction item (to detect drag start).
    - `onActiveChanged`: If active -> `appBridge.startDrag(selectionModel.selection)`.
- **Drop Handling**: `DropArea` (for dropping files *into* folders).
  - `onEntered`: Highlight verification.
  - `onDropped`: `appBridge.handleDrop` with `model.path`.

#### [MODIFY] [ui/qml/views/MasonryView.qml](file:///home/ray/Desktop/files/wrk/Imbric/ui/qml/views/MasonryView.qml)
- **Remove** complex hit-testing logic:
  - Delete `SelectionHelper.getMasonrySelection()` usage for clicks.
  - Delete complex `mapFromItem` coordinate translations for interactions.
  - Delete `startPath`, `isDragging`, `wasDragging` state variables from global MouseArea.
- **Simplify** `rubberBandArea`:
  - Purpose: Only handles actions that *miss* items.
  - `onPressed`: Start rubberband (only if `!itemHit` - though items will intercept now, so this is natural).
  - `onWheel` (Ctrl+Scroll): Preserve Zoom logic.
  - `onClicked`: `selectionModel.clear()`.
  - `onRightClicked`: `appBridge.showBackgroundContextMenu()`.
- **Integration**:
  - Replace inline `delegate: Item { ... }` with `delegate: Components.MasonryDelegate { ... }`.
  - Bind properties: `model`, `width`, `selected`, `isRenaming`.

### Core Logic (`core/`)

#### [MODIFY] [core/selection_helper.py](file:///home/ray/Desktop/files/wrk/Imbric/core/selection_helper.py)
*(Optional)* Clean up single-point selection logic if no longer needed, but `getMasonrySelection` is still needed for the rubberband rect. Minimal changes expected here, mostly just usage reduction.

---

## Verification Plan

### Automated Tests
*None available for QML input handling.*

### Manual Verification
1.  **Basic Interaction**:
    - [ ] Click file -> Selects.
    - [ ] Ctrl+Click -> Toggles selection.
    - [ ] Double Click -> Opens folder/file.
    - [ ] Right Click -> Shows Context Menu.
2.  **Focus Stability (The Fix)**:
    - [ ] Press F2 on a file.
    - [ ] **Verify**: Rename box appears.
    - [ ] Click *inside* the rename box (text cursor move).
    - [ ] **Verify**: Box does NOT disappear (Focus remains).
3.  **Drag & Drop**:
    - [ ] Drag file to desktop (System DnD).
    - [ ] Drag file into a folder within the same view.
    - [ ] **Verify**: Drop on folder vs Drop on background works (Z-order check).
4.  **Rubberband**:
    - [ ] Drag in empty space -> Draws rectangle -> Selects items.
    - [ ] Click empty space -> Clears selection.
