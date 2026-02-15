---

python3 tests/test_file_operations.py

============================================================
🧪 RUNNING FILE OPERATIONS TESTS
============================================================
  ✅ Basic Copy
  ✅ Basic Move
  ✅ Basic Trash (skipped on /tmp - expected)
  ✅ Create Folder
  ✅ Rename
  ✅ Parallel Operations
  ✅ Copy Directory
  ✅ Active Job Count
  ✅ Error Handling
  ✅ Cancel Operation
RESULTS: 10 passed, 0 failed

---
2. The "Hidden" Problem I Found (Partial Undo Validity)
The problem I identified is a Data Consistency Risk during Undo operations.

The Scenario:
Imagine you just moved 10 files to a new folder. You press 
Undo
. The Undo Manager starts moving them back, one by one.

File 1: Moved back. (Success)
File 2: Moved back. (Success)
File 3: FAILS (e.g., the file is open in another app, or permission denied).
The Code's Reaction (Current Logic):
Because one file failed, the 
UndoManager
 marks the entire batch as "Failed".

python
if not success:
    self._undo_stack.append(op)  # Puts the WHOLE batch of 10 files back on the Undo Stack
The Resulting State (The Bug):
Filesystem State: Mixed. Files 1 & 2 are in the "Old" folder. Files 3–10 are in the "New" folder.
Undo Stack State: It thinks all 10 files are still in the "New" folder.
The Danger:
If you try to press 
Undo
 again later:

It tries to move File 1 back. Error: It's already there! (Overwrite warning or failure).
It tries to move File 3 back. Error: It failed last time, it will probably fail again.
Recommendation:
This is an "Edge Case" (rareish), but dangerous. A robust fix would involve splitting the transaction on failure:

If Files 1 & 2 succeed, remove them from the Undo record.
Keep only Files 3–10 in the Undo stack (as a "Failed Remaining" batch).
Do you want me to implement this "Smart Split" logic to make the Undo system bulletproof?

----

You asked me to verify if specific problems exist:

Usage of kwargs:
Status: NOT IMPLEMENTED. FileOperations.py (which I read previously) explicitly lists transaction_id="" in 
copy
, 
move
, 
trash
, 
rename
, 
createFolder
.
Impact: Code is slightly more verbose than necessary, but functionally correct. It's a style/maintainability issue, not a bug.
AppBridge using Old Logic (Legacy Calls):
handleDrop
: Uses 
startTransaction
 and passes tid. CORRECT.
paste
: Uses 
startTransaction
 and passes tid. CORRECT.
showContextMenu
 (Trash): Uses 
startTransaction
 and passes tid. CORRECT.
renameFile
: Calls self.mw.file_ops.rename(old_path, final_name). MISSING TRANSACTION.
Renaming is a single atomic operation, so a "Batch" of 1 is implicitly created by 
TransactionManager
? No. 
FileOperations
 creates a 
FileJob
. If no transaction_id is passed, FileJob.transaction_id is empty. The 
TransactionManager
 ignores it.
Problem: Rename operations are NOT being recorded in the Undo History because they don't have a transaction ID!
**[RESOLVED 2026-02-04]**: `FileOperations.rename` and `createFolder` now accept `transaction_id`.

_create_new_folder
: Calls self.mw.file_ops.createFolder(folder_path). MISSING TRANSACTION.
Problem: Creating a new folder is NOT recorded in Undo History.
**[RESOLVED 2026-02-04]**: Fixed.

Summary of "Problems that Exist":

Rename & Create Folder are NOT undoable. (Because 
AppBridge
 calls them without starting a transaction). **[FIXED]**
Verbosity in 
FileOperations
. (Minor).
---

Navigation History is the "Back" and "Forward" buttons functionality, exactly like in a web browser or standard file manager.

How it works:
The Stack: It keeps a list of folders you have visited.
Start: ~/
Click 'Documents': ~/Documents (Stack: [~])
Click 'Work': ~/Documents/Work (Stack: [~, ~/Documents])
Back Button: Moves you to the previous folder in the stack (~/Documents) and adds ~/Documents/Work to a "Forward Stack".
Forward Button: Moves you back to ~/Documents/Work.
Why we need it:
Currently, Imbric only has a "Up" button (
ui/main_window.py
 line 76).

Up: Goes to parent folder ( ../ ).
Back: Goes to where you were a second ago.
Example Scenarios:

Without History: You are deep in ~/Photos/2023/Parties. You accidentally click "Home". To go back, you have to click Photos -> 2023 -> Parties again manually.
With History: You just click "Back".
Current Status:
**[IMPLEMENTED 2026-02-04]**: `NavigationManager` fully implements logic. `MainWindow` wiring pending.

Missing. 
MainWindow
 has 
navigate_to
 (Line 220), but it simply changes the path. It doesn't save where you came from.
Requirement: We need to implement a simple HistoryStack class (likely inside Tab) to track back_stack and forward_stack.

nalysis of 
ui/main_window.py
 confirms there is NO BUG.

Creation: Lines 29, 37, 40 create the managers.
python
29: self.file_ops = FileOperations()
37: self.undo_manager = UndoManager(file_operations=self.file_ops)
40: self.trash_manager = TrashManager()
Logic Injection: Line 54 explicitly injects the trash manager.
python
54: self.file_ops.setTrashManager(self.trash_manager)
Result:
FileOperations._trash_manager is NOT None.
The 
trash()
 method (lines 465-477 of 
file_operations.py
) will take the first branch (if self._trash_manager: return self._trash_manager.trash(...)).
The inline fallback code (lines 467-477) is effectively dead code (only reachable if initialization fails).


### 🚀 Android Device Integration (Experimental Alpha v0.6.0)

**Goal:** MTP device support via `android-file-transfer-linux` Python bindings.

- [ ] **Phase 1: Foundation** (Read-only device browsing)
  - [ ] Install & verify `android-file-transfer-linux` with Python bindings
  - [ ] Test thumbnail support: `ObjectInfo.ThumbFormat`, `ThumbPixWidth`, `ThumbPixHeight`
  - [ ] Create `core/mtp_bridge/` module structure
  - [ ] Implement `MTPDeviceManager` (device detection)
  - [ ] Implement `MTPScanner` (file listing compatible with `FileScanner` API)
  - [ ] Implement `MTPThumbnailProvider` (`get_thumb()` integration)
  - [ ] Modify `MainWindow` for `mtp://` path detection + scanner switching
  - [ ] Modify `SidebarModel` to show "Devices" section
  - [ ] Test with real Android device
- [ ] **Phase 2: Photo Transfer** (v0.7.0)
  - [ ] Implement `MTPFileOperations` (copy from device)
  - [ ] Wire up clipboard operations for MTP → Local copy
  - [ ] Progress tracking for large transfers
- [ ] **Phase 3: Advanced** (Backlog)
  - [ ] Bi-directional sync (upload to device)
  - [ ] Auto-detection on device plug-in
  - [ ] DCIM quick-import ("Import all photos" button)

**Why This Is Unique:** First Linux photo manager with native Android device browsing in same UI as local files!



Your current state:
1.  QML Cleanup (clearComponentCache, releaseResources): This is good practice for image-heavy apps. QML's texture cache can grow indefinitely if not managed. We are right to force this when leaving a heavy folder.
2.  Python GC (gc.collect()): This is neutral/safe. It just cleans up circular references immediately. Since we had a bug with circular references (the scanner), this is a good safety net, but strictly speaking, Python would do it eventually.
3.  malloc_trim (The Diagnostic Tool): This is the "aggressive" one. You are right—we probably should not run this on every navigation in production. It causes CPU spikes and fights the OS allocator.
---

## 5. Python-Managed Shortcuts in QML (The "Headless" Pattern)

This section explains the architectural decision to move shortcut handling **out** of QML and into Python `ActionManager`.

### The Concept: "Dumb View, Smart Controller"

In traditional QML apps, you often see:
```qml
// Traditional (The "Smart View")
Item {
    Keys.onPressed: (event) => {
        if (event.key == Qt.Key_F2) { startRename() }
    }
}
```
This looks simple, but it creates a **Focus Trap**. If a button inside the view steals focus, the shortcut stops working.

### The New Architecture: "Global Interception"

We moved to a **Centralized Python Controller**:

1.  **The Trigger (Python):** 
    We register `QAction`s in `ActionManager` using `Qt.WindowShortcut`. This means efficient, OS-level interception. The Python window catches the key *before* QML even knows it happened.

2.  **The Logic (Python):**
    We don't ask QML "what is selected?". We ask our own `FileManager` (which tracks selection state in Python).
    *   Python: "User pressed F2. What is selected? -> `photo.jpg`."
    *   Python: "Okay, rename `photo.jpg`."

3.  **The Command (Signal):**
    Python sends a specific instruction to QML via `AppBridge`:
    *   `appBridge.renameRequested.emit("photo.jpg")`

4.  **The Reaction (QML):**
    QML receives the order and updates its visual state.
    ```qml
    // Modern (The "Dumb View")
    Connections {
        target: appBridge
        onRenameRequested: (path) => { 
            root.pathBeingRenamed = path // Show text box
        }
    }
    ```

### Why we did this (Pros & Cons)

| Feature | Old Way (QML Keys) | New Way (Python Actions) |
| :--- | :--- | :--- |
| **Reliability** | ⚠️ Flaky (depends on focus) | ✅ Rock Solid (Window-scope) |
| **State Sync** | ⚠️ Hard (QML must tell Python) | ✅ Perfect (Python tells QML) |
| **Configurability**| ❌ Hardcoded in `.qml` file | ✅ Editable in `shortcuts.py` |
| **Complexity** | Simple (1 file) | Medium (Need Signals & Slots) |

**Verdict:** Use this pattern for all **App-Level Tools** (Rename, Delete, Copy). Only use `Keys.onPressed` for purely internal navigation (Arrow keys, Enter to open).


[FAST] [SCOPE: Evaluate QImageReader vs Native/Custom solutions for thumbnail generation]

QImageReader is "Good Enough" for 95% of cases, but not "World Class" for high-performance gallery apps.

1. QImageReader (The Built-in)
Pros: Native to Qt, easy to implement (setScaledSize), supports many formats.
Cons:
Synchronous-ish: Even in a thread, it blocks that thread fully.
CPU Bound: All decoding happens on the CPU.
Format Limits: Great for JPEG/PNG. Terrible for RAW (needs plugins), HEIF/HEIC (slow), or Videos (impossible).
2. The Power User / "State of the Art" Solutions
If we want lightning fast, buttery smooth resizing for a "Photo First" app, we look at these tiers:

Tier A: Native Accelerated Decoding (OS Level)
Using the OS's native tooling often beats generic libraries because they use hardware acceleration (GPU/Media Engines).

Linux: GdkPixbuf (which GnomeDesktopThumbnailFactory uses). This is what Nautilus uses. It's solid but not always GPU-accelerated.
Alternative: FFmpeg (via python bindings like 
av
 or opencv).
Why? FFmpeg is hyper-optimized. It can extract video frames OR decode images significantly faster than Qt's internal engines for obscure formats.
Downside: Heavy dependency.
Tier B: "Vips" (libvips) — The Speed King
If you want to resize a 50MP image to 500px instantly using minimal RAM, libvips is the industry standard (used by Wikipedia, Flickr, etc.).

Why: It streams the image. It never loads the whole file. It reads-and-resizes on the fly in small chunks.
Performance: Often 5x-10x faster than ImageMagick or Qt for large resize ops.
Memory: Constant, low memory usage regardless of image size.
Tier C: GPU Decoding
Using OpenGL / Vulkan to decode.

This is theoretically fastest but incredibly complex to implement correctly for generic file formats (Texture upload bandwidth often negates the speed gain for static images). This is usually overkill unless doing video playback.
Recommendation for Imbric
Stick to GnomeDesktopThumbnailFactory (Tier A) for standard sizes (128/256).
It's robust, compliant, and "free" (system does it).
For Detail Zoom (>256px), Upgrade to libvips (Tier B).
If the user zooms in, we spawn a task that uses pyvips (if installed) to grab the 512px/1024px version.
Fallback: If pyvips isn't there, fall back to QImageReader.
Why not just QImageReader? QImageReader is fine for JPEGs. It will choke on a 40MB RAW file or a 100MB TIFF. Imbric (as a photo manager) will encounter these. A "Power User" tool needs to handle the heavy stuff gracefully.

[COMPLETE] Decision: Implemented `QImageReader` (Header Only) in `scanner.py` for Phase 1.
Reasoning: It is sufficient for the Justified Grid layout needs (Phase 1) and avoids adding heavy dependencies like `libvips` immediately. We can upgrade to Tier B later if performance on huge folders becomes an issue.
Status: **IMPLEMENTED (2026-02-05)**

6. IconImage vs ThemeImageProvider (Architecture Decision)

The "Icon Architecture" work (2026-02-01) established a critical performance rule:

**The Rule:**
- **Buttons (5-10 items):** Use `QtQuick.Controls.IconImage` (Native, simple).
- **Data Grids (1000+ items):** Use `ThemeImageProvider` (Backend, cache-friendly).

**Why?**
`IconImage` in QML does not share a bitmap cache efficiently between 500 instances of "folder-icon".
`ThemeImageProvider` (Python/C++) renders the icon ONCE into the global Qt Pixmap Cache. 500 delegates then share the same texture pointer.

**Verdict:** Always use `image://theme/` provider for grid views.


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

Silent Partial Failure Fix
Changes Implemented
ui/elements/progress_overlay.py
Component    Change
onOperationCompleted
Added logic to parse `dest
Visuals    Added Warning State: Red text, "dialog-warning" icon.
Behavior    Auto-hide disabled when errors occur. Requires manual dismissal.
Controls    Cancel button repurposes as "Dismiss" (Close) button in error state.
Verification Steps (Manually)
Preparation: Create a folder with one locked file (000 permissions) and one normal file.
Action: Copy this folder to another location using Imbric.
Observation:
 Progress bar finishes.
 Overlay remains visible (does not vanish).
 Icon is a ⚠️ (Warning Triangle).
 Text says: "Done (1 files skipped)" in red.
 "Stop" button changes to a "Close" (X) button.
Dismiss: Click the "X" button. The overlay should close.

{add this as a feature that user can turn on and off in future-         TapHandler {
            acceptedButtons: Qt.RightButton
            acceptedModifiers: Qt.KeyboardModifierMask
            gesturePolicy: TapHandler.WithinBounds
            onTapped: {
                selectionModel.clear()-- this
                if (root.bridge) root.bridge.showBackgroundContextMenu()
            }
        }}


 python3 -c "from PySide6.QtCore import Qt; print(dir(Qt))" | grep KeyboardModifier

['AlignmentFlag', 'AnchorPoint', 'ApplicationAttribute', 'ApplicationState', 'ArrowType', 'AspectRatioMode', 'Axis', 'BGMode', 'BrushStyle', 'CaseSensitivity', 'CheckState', 'ChecksumType', 'ClipOperation', 'ColorScheme', 'ConnectionType', 'ContextMenuPolicy', 'ContextMenuTrigger', 'ContrastPreference', 'CoordinateSystem', 'Corner', 'CursorMoveStyle', 'CursorShape', 'DateFormat', 'DayOfWeek', 'DockWidgetArea', 'DockWidgetAreaSizes', 'DropAction', 'Edge', 'EnterKeyType', 'EventPriority', 'FillRule', 'FindChildOption', 'FocusPolicy', 'FocusReason', 'GestureFlag', 'GestureState', 'GestureType', 'GlobalColor', 'HighDpiScaleFactorRoundingPolicy', 'HitTestAccuracy', 'ImageConversionFlag', 'InputMethodHint', 'InputMethodQuery', 'ItemDataRole', 'ItemFlag', 'ItemSelectionMode', 'ItemSelectionOperation', 'Key', 'KeyboardModifier', 'LayoutDirection', 'MaskMode', 'MatchFlag', 'Modifier', 'MouseButton', 'MouseEventFlag', 'MouseEventSource', 'NativeGestureType', 'NavigationMode', 'Orientation', 'PenCapStyle', 'PenJoinStyle', 'PenStyle', 'PermissionStatus', 'ReturnByValueConstant', 'ScreenOrientation', 'ScrollBarPolicy', 'ScrollPhase', 'ShortcutContext', 'SizeHint', 'SizeMode', 'SortOrder', 'SplitBehaviorFlags', 'TabFocusBehavior', 'TextElideMode', 'TextFlag', 'TextFormat', 'TextInteractionFlag', 'TileRule', 'TimeSpec', 'TimerId', 'TimerType', 'ToolBarArea', 'ToolBarAreaSizes', 'ToolButtonStyle', 'TouchPointState', 'TransformationMode', 'UIEffect', 'WhiteSpaceMode', 'WidgetAttribute', 'WindowFrameSection', 'WindowModality', 'WindowState', 'WindowType', '__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', 'beginPropertyUpdateGroup', 'bin', 'bom', 'center', 'dec', 'endPropertyUpdateGroup', 'endl', 'fixed', 'flush', 'forcepoint', 'forcesign', 'hex', 'left', 'lowercasebase', 'lowercasedigits', 'noforcepoint', 'noforcesign', 'noshowbase', 'oct', 'reset', 'right', 'scientific', 'showbase', 'uppercasebase', 'uppercasedigits', 'ws']

ray@desktop:~/Desktop/files/wrk/Imbric$ python3 -c "from PySide6.QtGui import QGuiApplication; print(dir(QGuiApplication))" | grep keyboardModifiers
['ApplicationFlags', '__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', 'aboutToQuit', 'addLibraryPath', 'allWindows', 'applicationDirPath', 'applicationDisplayName', 'applicationDisplayNameChanged', 'applicationFilePath', 'applicationName', 'applicationNameChanged', 'applicationPid', 'applicationState', 'applicationStateChanged', 'applicationVersion', 'applicationVersionChanged', 'arguments', 'blockSignals', 'changeOverrideCursor', 'checkPermission', 'childEvent', 'children', 'clipboard', 'closingDown', 'commitDataRequest', 'connect', 'connectNotify', 'customEvent', 'deleteLater', 'desktopFileName', 'desktopSettingsAware', 'destroyed', 'devicePixelRatio', 'disconnect', 'disconnectNotify', 'dumpObjectInfo', 'dumpObjectTree', 'dynamicPropertyNames', 'emit', 'event', 'eventDispatcher', 'eventFilter', 'exec', 'exec_', 'exit', 'findChild', 'findChildren', 'focusObject', 'focusObjectChanged', 'focusWindow', 'focusWindowChanged', 'font', 'fontChanged', 'fontDatabaseChanged', 'highDpiScaleFactorRoundingPolicy', 'inherits', 'inputMethod', 'installEventFilter', 'installNativeEventFilter', 'installTranslator', 'instance', 'instanceExists', 'isLeftToRight', 'isQuickItemType', 'isQuitLockEnabled', 'isRightToLeft', 'isSavingSession', 'isSessionRestored', 'isSetuidAllowed', 'isSignalConnected', 'isWidgetType', 'isWindowType', 'keyboardModifiers', 'killTimer', 'lastWindowClosed', 'layoutDirection', 'layoutDirectionChanged', 'libraryPaths', 'metaObject', 'modalWindow', 'mouseButtons', 'moveToThread', 'nativeInterface', 'notify', 'objectName', 'objectNameChanged', 'organizationDomain', 'organizationDomainChanged', 'organizationName', 'organizationNameChanged', 'overrideCursor', 'palette', 'paletteChanged', 'parent', 'platformFunction', 'platformName', 'postEvent', 'primaryScreen', 'primaryScreenChanged', 'processEvents', 'property', 'queryKeyboardModifiers', 'quit', 'quitOnLastWindowClosed', 'receivers', 'removeEventFilter', 'removeLibraryPath', 'removeNativeEventFilter', 'removePostedEvents', 'removeTranslator', 'requestPermission', 'resolveInterface', 'restoreOverrideCursor', 'saveStateRequest', 'screenAdded', 'screenAt', 'screenRemoved', 'screens', 'sendEvent', 'sendPostedEvents', 'sender', 'senderSignalIndex', 'sessionId', 'sessionKey', 'setApplicationDisplayName', 'setApplicationName', 'setApplicationVersion', 'setAttribute', 'setBadgeNumber', 'setDesktopFileName', 'setDesktopSettingsAware', 'setEventDispatcher', 'setFont', 'setHighDpiScaleFactorRoundingPolicy', 'setLayoutDirection', 'setLibraryPaths', 'setObjectName', 'setOrganizationDomain', 'setOrganizationName', 'setOverrideCursor', 'setPalette', 'setParent', 'setProperty', 'setQuitLockEnabled', 'setQuitOnLastWindowClosed', 'setSetuidAllowed', 'setWindowIcon', 'shutdown', 'signalsBlocked', 'startTimer', 'startingUp', 'staticMetaObject', 'styleHints', 'sync', 'testAttribute', 'thread', 'timerEvent', 'topLevelAt', 'topLevelWindows', 'tr', 'translate', 'windowIcon']
ray@desktop:~/Desktop/files/wrk/Imbric$ 
y@desktop:~/Desktop/files/wrk/Imbric$ /usr/bin/python3 -c "from PySide6.QtGui import QGuiApplication; print(dir(QGuiApplication))" | grep keyboardModifiers
['ApplicationFlags', '__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', 'aboutToQuit', 'addLibraryPath', 'allWindows', 'applicationDirPath', 'applicationDisplayName', 'applicationDisplayNameChanged', 'applicationFilePath', 'applicationName', 'applicationNameChanged', 'applicationPid', 'applicationState', 'applicationStateChanged', 'applicationVersion', 'applicationVersionChanged', 'arguments', 'blockSignals', 'changeOverrideCursor', 'checkPermission', 'childEvent', 'children', 'clipboard', 'closingDown', 'commitDataRequest', 'connect', 'connectNotify', 'customEvent', 'deleteLater', 'desktopFileName', 'desktopSettingsAware', 'destroyed', 'devicePixelRatio', 'disconnect', 'disconnectNotify', 'dumpObjectInfo', 'dumpObjectTree', 'dynamicPropertyNames', 'emit', 'event', 'eventDispatcher', 'eventFilter', 'exec', 'exec_', 'exit', 'findChild', 'findChildren', 'focusObject', 'focusObjectChanged', 'focusWindow', 'focusWindowChanged', 'font', 'fontChanged', 'fontDatabaseChanged', 'highDpiScaleFactorRoundingPolicy', 'inherits', 'inputMethod', 'installEventFilter', 'installNativeEventFilter', 'installTranslator', 'instance', 'instanceExists', 'isLeftToRight', 'isQuickItemType', 'isQuitLockEnabled', 'isRightToLeft', 'isSavingSession', 'isSessionRestored', 'isSetuidAllowed', 'isSignalConnected', 'isWidgetType', 'isWindowType', 'keyboardModifiers', 'killTimer', 'lastWindowClosed', 'layoutDirection', 'layoutDirectionChanged', 'libraryPaths', 'metaObject', 'modalWindow', 'mouseButtons', 'moveToThread', 'nativeInterface', 'notify', 'objectName', 'objectNameChanged', 'organizationDomain', 'organizationDomainChanged', 'organizationName', 'organizationNameChanged', 'overrideCursor', 'palette', 'paletteChanged', 'parent', 'platformFunction', 'platformName', 'postEvent', 'primaryScreen', 'primaryScreenChanged', 'processEvents', 'property', 'queryKeyboardModifiers', 'quit', 'quitOnLastWindowClosed', 'receivers', 'removeEventFilter', 'removeLibraryPath', 'removeNativeEventFilter', 'removePostedEvents', 'removeTranslator', 'requestPermission', 'resolveInterface', 'restoreOverrideCursor', 'saveStateRequest', 'screenAdded', 'screenAt', 'screenRemoved', 'screens', 'sendEvent', 'sendPostedEvents', 'sender', 'senderSignalIndex', 'sessionId', 'sessionKey', 'setApplicationDisplayName', 'setApplicationName', 'setApplicationVersion', 'setAttribute', 'setBadgeNumber', 'setDesktopFileName', 'setDesktopSettingsAware', 'setEventDispatcher', 'setFont', 'setHighDpiScaleFactorRoundingPolicy', 'setLayoutDirection', 'setLibraryPaths', 'setObjectName', 'setOrganizationDomain', 'setOrganizationName', 'setOverrideCursor', 'setPalette', 'setParent', 'setProperty', 'setQuitLockEnabled', 'setQuitOnLastWindowClosed', 'setSetuidAllowed', 'setWindowIcon', 'shutdown', 'signalsBlocked', 'startTimer', 'startingUp', 'staticMetaObject', 'styleHints', 'sync', 'testAttribute', 'thread', 'timerEvent', 'topLevelAt', 'topLevelWindows', 'tr', 'translate', 'windowIcon']