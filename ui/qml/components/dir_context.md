Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/ui/qml/components
Reusable QML components used to construct the main views. Components here handle their own internal states (hover, physics, styling) and expose clean declarative APIs for the views to consume.

Rules:
- Components should never make direct `import services` calls. They must receive data and bridge references via properties injected by the parent View.
- Keep components agnostic to the Application scope. If it needs business logic, emit a signal.
- Always use `SystemPalette` or `Material` properties for theming; never hardcode colors unless deriving an alpha value from a system color.

Index:
- internal: Contains private helper components.

### [FILE: FileDelegate.qml] [DONE]
Role: Represents a single file or folder in the grid layout, handling its own selection visual state, context menus, and drag-and-drop initiation.

/DNA/: [TapHandler(left)] + [TapHandler(right)] + [HoverHandler] + [DragHandler] + [DropArea] + [RenameField] -> em:clicked/doubleClicked/renameCommitted

- SrcDeps: components.RenameField
- SysDeps: QtQuick, QtQuick.Controls

API:
  - FileDelegate(Item):
    - clicked(button, modifiers) -> signal: Emits when tapped (left or right).
    - doubleClicked() -> signal: Emits on double-tap.
    - renameCommitted(newName) -> signal: Emits when inline rename completes.
    - renameCancelled() -> signal: Emits when inline rename is aborted.
!Caveat: Thumbnail downscaling (mipmap: false) is intentionally disabled for sharper images; sourceSize is disabled to prevent cache thrashing on window resize.

### [FILE: GtkScrollBar.qml] [DONE]
Role: A custom physics-enabled, auto-hiding scrollbar that mirrors GNOME/GTK behavior with expanding thumbs on hover.

/DNA/: [WheelHandler] -> call:handleWheel() -> [acceleration_logic] -> flickable.contentY ++ [activityTimer] -> hide()

- SrcDeps: none
- SysDeps: QtQuick, QtQuick.Controls

API:
  - GtkScrollBar(ScrollBar):
    - handleWheel(event) -> void: Public function called by parent view's WheelHandler to process custom physics.

### [FILE: GtkTabBar.qml] [DONE]
Role: Container for draggable, closable tabs matching a native header bar look.

/DNA/: [RowLayout] -> [{TabBar} -> {Repeater} -> {GtkTabButton}] + [ToolButton(add)] -> em:addClicked/tabClosed

- SrcDeps: components.GtkTabButton
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts

API:
  - GtkTabBar(Item):
    - addClicked() -> signal: Emits when the '+' button is pressed.
    - tabClosed(index) -> signal: Emits when a tab's close button is clicked.

### [FILE: GtkTabButton.qml] [DONE]
Role: Individual tab button with elastic width, hover states, and a built-in close button.

/DNA/: [TabButton] -> {RowLayout} -> [{Label} + {ToolButton(close)} -> em:closeClicked]

- SrcDeps: none
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts

API:
  - GtkTabButton(TabButton):
    - closeClicked() -> signal: Emits when the native styled close 'x' is clicked.

### [FILE: RenameField.qml] [DONE]
Role: Inline text entry field for renaming items, handling focus loss and enter/escape key presses.

/DNA/: [TextField] -> initSession() -> select(name_only) -> [onAccepted|onActiveFocusChanged(false)] -> em:commit -> [onEscape] -> em:cancel

- SrcDeps: none
- SysDeps: QtQuick, QtQuick.Controls

API:
  - RenameField(TextField):
    - commit(newName) -> signal: Emits when the user confirms the new name.
    - cancel() -> signal: Emits when the user aborts.
!Caveat: Automatically selects the filename while ignoring the extension upon activation.

### [FILE: RowDelegate.qml] [DONE]
Role: A horizontal row container used by ListView. Instantiates multiple FileDelegates per row based on injected modelData.

/DNA/: [Row] -> [Repeater(modelData)] -> [ItemWrapper] -> [FileDelegate]

- SrcDeps: components.FileDelegate
- SysDeps: QtQuick, QtQuick.Layouts

API:
  - RowDelegate(Row):
!Caveat: Calculates `columnWidth` dynamically based on aspect ratio while enforcing constraints like `thumbnailMaxWidth`.

### [FILE: RubberBand.qml] [DONE]
Role: Reusable visual selection rectangle matching native QRubberBand behavior natively in QML.

/DNA/: [Rectangle] -> call:update(x,y,w,h)

- SrcDeps: none
- SysDeps: QtQuick

API:
  - RubberBand(Rectangle):
    - update(startX, startY, currentX, currentY) -> void: Recalculates geometry between two points.
    - show() -> void: Makes the rubberband visible.
    - hide() -> void: Hides the rubberband.
    - getRect() -> object: Returns {x, y, width, height}.

### [FILE: SelectionModel.qml] [DONE]
Role: Headless controller managing the array of currently selected file paths. Implements standard file browser Ctrl/Shift click logic.

/DNA/: [QtObject] -> call:handleClick(path, ctrl, shift) -> _computeRange() + [selection_array] ++

- SrcDeps: none
- SysDeps: QtQuick

API:
  - SelectionModel(QtObject):
    - handleClick(path, ctrl, shift, allItems) -> void: Main entry point for processing clicks and updating selection.
    - isSelected(key) -> bool: Checks if a path is currently selected.
    - clear() -> void: Empties selection.
    - selectRange(keys, append) -> void: Batch selection, typically used by Marquee/Rubberband.

### [FILE: Sidebar.qml] [DONE]
Role: Collapsible side panel rendering sections (Quick Access, Devices) from a unified `sidebarModel` (QAbstractListModel) injected by Python.

/DNA/: [property var sectionsModel] -> [ScrollView] -> [Column] -> [Repeater(model)] -> [SidebarHeader] + [Loader -> GtkGrid|GtkList -> SidebarItem(model.itemsModel)]

- SrcDeps: components.SidebarHeader, components.SidebarItem, components.GtkScrollBar
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts, QtQuick.Controls.Material

API:
  - Sidebar(Pane):
    - navigationRequested(path) -> signal: Emits when a directory/bookmark is selected.
    - mountRequested(identifier) -> signal: Emits when an unmounted volume is clicked.
    - unmountRequested(identifier) -> signal: Emits when an eject icon is clicked.
    - sectionActionTriggered(title, action) -> signal: Emits when a header tool button (e.g. Add, Settings) is clicked.
    - sectionToggled(title, collapsed) -> signal: Emits when a section expands or collapses.

### [FILE: SidebarHeader.qml] [DONE]
Role: The top bar of a Sidebar section containing the toggle arrow, section name, and contextual action buttons (e.g. Add, Settings).

/DNA/: [HoverHandler] -> [dwellTimer|collapseTimer] -> flag:internalHovered -> [TapHandler] -> em:toggleCollapsed

- SrcDeps: none
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts, QtQuick.Controls.Material

API:
  - SidebarHeader(Item):
    - toggleCollapsed() -> signal: Emits when the user clicks the header to expand/collapse the section.

### [FILE: SidebarItem.qml] [DONE]
Role: Generic interactive row delegate for Sidebar lists (e.g. representing a Volume). Includes visual support for usage bars and mount status.

/DNA/: [ItemDelegate] -> {RowLayout} -> [{Icon} + {Label+UsageBar} + {ExtensionArea(default_slot)}] -> em:clicked

- SrcDeps: none
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts, QtQuick.Controls.Material

API:
  - SidebarItem(ItemDelegate):
    - clicked() -> signal: Standard inherited signal from ItemDelegate.

### [FILE: Sidebar_Legacy.qml] [DEPRECATED]
Role: Legacy hardcoded version of the Sidebar. Kept for reference.
