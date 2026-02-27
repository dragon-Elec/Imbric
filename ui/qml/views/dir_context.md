Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/ui/qml/views
Central views that assemble components into primary layouts (Main Layout, Tabs, File Grids).

Rules:
- Views should assemble smaller components rather than implementing granular UI details directly.
- Use explicit bindings where possible, but rely on per-tab controllers or implicit context properties (like `tabManager`, `bridge`) where data varies by context.

Atomic Notes:
!Pattern: [Controller Injection] - Reason: TabContainer dynamically instantiates views from `tabModel` and injects per-tab controllers to instance views cleanly without global singletons.

Index:

### [FILE: JustifiedView.qml] [DONE]
Role: Main native row-based file grid supporting fast scrolling, marquee selection, and drag-and-drop.

/DNA/: [Connections:rowBuilder] + [DropArea] + [ListView -> RowDelegate] + [DragHandler:marquee -> rubberBand + selectionModel]

- SrcDeps: components.RowDelegate, components.SelectionModel, components.GtkScrollBar, components.RubberBand
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts

API:
  - JustifiedView(Item):
    - selectPaths(paths) -> void: Updates view selection to specific paths.
    - selectAll() -> void: Selects all items currently loaded in view.

### [FILE: MainLayout.qml] [DONE]
Role: Top-level horizontal split view managing the sidebar pane and main tabbed view pane.

/DNA/: [SplitView] -> [{Sidebar} + {TabContainer}] -> [em:navigationRequested]

- SrcDeps: components.Sidebar, TabContainer
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts

API:
  - MainLayout(Item):
    - navigationRequested(path) -> void: Emits when sidebar navigates.
    - mountRequested(identifier) -> void: Emits when mounting a drive/volume.
    - unmountRequested(identifier) -> void: Emits when unmounting a volume.
    - sectionToggled(title, collapsed) -> void: Emits when sidebar section shrinks/expands.
!Caveat: Assumes `sidebarModel` (QAbstractListModel) is provided directly to instance or via ShellManager context property.

### [FILE: TabContainer.qml] [DONE]
Role: Wraps the tab bar and content stack to swap active views and inject per-tab controllers.

/DNA/: [ColumnLayout] -> [{GtkTabBar} + {StackLayout:Repeater(tabModel) -> tabController -> JustifiedView}]

- SrcDeps: components.GtkTabBar, JustifiedView
- SysDeps: QtQuick, QtQuick.Controls, QtQuick.Layouts

API:
  - TabContainer(Item):
!Caveat: Heavily relies on context properties `tabModel` and `tabManager` implicitly provided by the Python runtime context.
