import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import components as Components

Item {
    id: window
    
    // --- DI from ShellManager ---
    // property var shellManager (Implicit)
    // property var tabManager (Implicit)
    // property var tabModel (Implicit)
    
    // --- Data Models for Sidebar ---
    // Unified model provided by ShellManager as a QAbstractListModel on Context
    // property var sidebarModel (Implicit via engine.rootContext)
    
    // --- Signals for ShellManager ---
    signal navigationRequested(string path)
    signal mountRequested(string identifier)
    signal unmountRequested(string identifier)
    signal sectionToggled(string title, bool collapsed)
    
    // --- System Palette ---
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }
    readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    
    // --- PERSISTENCE ---
    Settings {
        id: layoutSettings
        category: "Interface"
        property alias sidebarWidth: sidebar.width
    }

    // --- MAIN SPLIT VIEW ---
    SplitView {
        id: splitView
        anchors.fill: parent
        orientation: Qt.Horizontal
        
        handle: Rectangle {
            implicitWidth: 10
            color: sysPalette.window
            
            // Subtle Accent background for the handle area
            Rectangle {
                anchors.fill: parent
                color: sysPalette.highlight
                opacity: 0.18
            }
        }

        Components.Sidebar {
            id: sidebar
            SplitView.minimumWidth: 150
            SplitView.maximumWidth: 400
            width: 225 // Initial default, overridden by Settings if exists
            
            // Note: SplitView prefers 'width' for persistence via alias.
            // SplitView.preferredWidth is used for initial layout logic, 
            // but for simple persistence, binding to 'width' is more reliable in Qt 6.
            
            // Pass Unified Data directly from context property
            sectionsModel: sidebarModel
            
            // Pass Actions up to ShellManager
            onNavigationRequested: (path) => window.navigationRequested(path)
            onMountRequested: (id) => window.mountRequested(id)
            onUnmountRequested: (id) => window.unmountRequested(id)
            
            // Handle Collapse State Persistence
            // Sidebar.qml needs to emit a signal for this, which we will add.
            // For now, if Sidebar doesn't have it, we can't connect it yet.
            // Assuming we will add onSectionToggled to Sidebar.qml next.
            // onSectionToggled: (title, collapsed) => window.sectionToggled(title, collapsed)
            
            // Sync Selection from Tabs (Optional: if we want sidebar to track active tab)
            Connections {
                target: tabManager
                function onCurrentPathChanged(path) {
                    sidebar.syncToPath(path)
                }
            }
        }

        // 2. TAB CONTAINER PANE
        TabContainer {
            id: mainView
            SplitView.fillWidth: true
            
            // It uses context properties (tabManager, tabModel) internally
        }
    }
}
