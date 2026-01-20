# Known Bug: F2 Inline Rename Sporadic Focus Loss

## Status: WONTFIX (QML Framework Limitation)

## Symptoms
- User selects file → presses F2 → rename TextArea appears
- TextArea receives `activeFocus=true`
- **Immediately** (same event loop) TextArea loses focus (`activeFocus=false`)
- Rename closes before user can type

## Trigger Conditions
- Sporadic, ~1 in 15-20 F2 presses
- More likely when rapidly clicking items then pressing F2
- Specific items not deterministic

## Technical Analysis

### Root Cause
QML's `Loader` component causes transient focus events when switching between `sourceComponent` values. The focus system fires `onActiveFocusChanged` with `activeFocus=false` during internal component lifecycle, even though no user action occurred.

### Event Sequence (from debug logs)
```
1. F2 pressed → pathBeingRenamed = selectedPath
2. Loader switches: textComponent → renameComponent  
3. TextArea.Component.onCompleted → forceActiveFocus()
4. onActiveFocusChanged: activeFocus=true  ✓
5. [QML INTERNAL] onActiveFocusChanged: activeFocus=false  ✗
   └── No TapHandler, MouseArea, or user interaction logged
6. If using auto-commit-on-blur: commit() fires, rename closes
```

### Attempted Fixes
| Approach | Result |
|:---------|:-------|
| Remove `forceActiveFocus()` from rubberBandArea | ❌ Bug persists |
| Add `FocusScope` wrapper | ❌ Same behavior |
| Debounce Timer (100ms) | ❌ Focus still lost after timer |
| Check `isOnItem` before stealing focus | ❌ Hit-test intermittently fails |
| Remove `onActiveFocusChanged` entirely | ✅ **Workaround applied** |

## Current Workaround
Removed `onActiveFocusChanged` handler. Rename now commits **only** via:
- **Enter/Return** → Commit
- **Escape** → Cancel
- **F2 again** → Toggle off (cancel)

Clicking elsewhere does NOT auto-commit (user must press Enter).

## Code Location
- `ui/qml/views/MasonryView.qml`: Lines 196-270 (Loader + TextArea)

## Related
- Qt Bug Reports: Focus issues with Loader are well-documented in Qt forums
- Similar issues in Qt Quick Controls 2 TextField inside Loader


user notes- i had discovered some bugs during this. 
🧪 Dir-Over-Dir Bug — Reproduce Steps
Create a test folder: ~/Test/FolderA/ with some files inside
Create a duplicate: ~/Backup/FolderA/ (same name)
In Imbric, navigate to ~/Test/
Cut FolderA
Navigate to ~/Backup/
Paste
Expected: Conflict dialog asks: Merge? Replace? Skip? Actual (suspected): Error, silent failure, or incorrect behavior

Please test and report what happens.

**i to do it again, they are visual bugs**