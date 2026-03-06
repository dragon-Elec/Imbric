import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import components as Components

Control {
    id: window
    padding: 0
    background: Rectangle { color: "transparent" } // Invisible surface to capture hover events
    hoverEnabled: true
    // --- DI from ShellManager ---
    // property var shellManager (Implicit)
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

    // --- MAIN LAYOUT ---
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 1. GLOBAL NAVIGATION BAR (Spans both Sidebar and Content)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            color: isSystemDark ? Qt.darker(sysPalette.window, 1.2) : Qt.lighter(sysPalette.window, 1.05)
            
            // Subtle Bottom border
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: sysPalette.window
                opacity: 0.5
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                // Left: Navigation Controls
                Row {
                    spacing: 4
                    Layout.alignment: Qt.AlignVCenter
                    
                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("GO_BACK") : "go-previous-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        enabled: shellManager && shellManager.current_pane ? shellManager.current_pane.canGoBack : false
                        onClicked: if (shellManager) shellManager.go_back()
                    }
                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("GO_FORWARD") : "go-next-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        enabled: shellManager && shellManager.current_pane ? shellManager.current_pane.canGoForward : false
                        onClicked: if (shellManager) shellManager.go_forward()
                    }
                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("GO_UP") : "go-up-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        enabled: shellManager && shellManager.current_pane ? shellManager.current_pane.canGoUp : false
                        onClicked: if (shellManager) shellManager.go_up()
                    }
                }

                // Center: Breadcrumb Address Bar
                Components.BreadcrumbAddressBar {
                    id: addressBar
                    objectName: "addressBar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    Layout.alignment: Qt.AlignVCenter

                    currentPath: shellManager && shellManager.current_pane ? shellManager.current_pane.currentPath : ""
                    pathSegments: shellManager && shellManager.current_pane ? shellManager.current_pane.pathSegments : []
                    palette: sysPalette
                    textColor: isSystemDark ? "white" : "black"

                    onPathRequested: (path) => { if (shellManager) shellManager.navigate_to(path) }

                    Connections {
                        target: shellManager && shellManager.current_pane ? shellManager.current_pane : null
                        function onPathRejected() {
                            addressBar.rejectPathError()
                        }
                        function onPathChanged(path) {
                            if (addressBar.isEditing) {
                                addressBar.isEditing = false
                            }
                        }
                    }

                    Connections {
                        target: shellManager
                        function onFocusAddressBarRequested() {
                            addressBar.isEditing = !addressBar.isEditing
                        }
                    }
                }
                
                // Right: Actions (Zoom & Edit)
                Row {
                    spacing: 4
                    Layout.alignment: Qt.AlignVCenter
                    visible: !addressBar.isEditing
                    
                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("ZOOM_OUT") : "zoom-out-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        onClicked: {
                            if (shellManager && shellManager.current_pane) {
                                shellManager.current_pane.appBridge.zoom(-1)
                            }
                        }
                        background: Rectangle { 
                            color: parent.down ? sysPalette.mid : (parent.hovered ? Qt.alpha(sysPalette.highlight, 0.1) : "transparent")
                            radius: 4 
                        }
                    }
                    
                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("ZOOM_IN") : "zoom-in-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        onClicked: {
                            if (shellManager && shellManager.current_pane) {
                                shellManager.current_pane.appBridge.zoom(1)
                            }
                        }
                        background: Rectangle { 
                            color: parent.down ? sysPalette.mid : (parent.hovered ? Qt.alpha(sysPalette.highlight, 0.1) : "transparent")
                            radius: 4 
                        }
                    }

                    ToolButton {
                        icon.name: (typeof actionManager !== 'undefined') ? actionManager.get_icon("EDIT") : "document-edit-symbolic"
                        icon.width: 16; icon.height: 16
                        width: 32; height: 32
                        onClicked: addressBar.isEditing = true
                        
                        background: Rectangle { 
                            color: parent.down ? sysPalette.mid : (parent.hovered ? Qt.alpha(sysPalette.highlight, 0.1) : "transparent")
                            radius: 4 
                        }
                    }
                }
            }
        }

        // 2. MAIN SPLIT VIEW
        SplitView {
            id: splitView
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            
            handle: Rectangle {
                implicitWidth: 7
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
                
                // Pass Unified Data directly from context property
                sectionsModel: sidebarModel
                
                // Pass Actions up to ShellManager
                onNavigationRequested: (path) => window.navigationRequested(path)
                onMountRequested: (id) => window.mountRequested(id)
                onUnmountRequested: (id) => window.unmountRequested(id)
                
                // Sync Selection from Tabs (Optional: if we want sidebar to track active tab)
                Connections {
                    target: shellManager
                    function onCurrentPathChanged(path) {
                        sidebar.syncToPath(path)
                    }
                }
            }

            // TAB CONTAINER PANE (Content Only now)
            TabContainer {
                id: mainView
                SplitView.fillWidth: true
                // It uses context properties internally
            }
        }
    }

    // --- Focus Management ---
    // Passive click-outside observer to dismiss address bar.
    TapHandler {
        enabled: addressBar.isEditing
        gesturePolicy: TapHandler.ReleaseWithinBounds // Prevents stealing 'press' from children
        onTapped: (eventPoint) => {
            var globalPos = addressBar.mapToItem(window, 0, 0)
            // Strict bounding box check to ensure we never trigger inside the bar
            if (eventPoint.position.x < globalPos.x || eventPoint.position.x > globalPos.x + addressBar.width ||
                eventPoint.position.y < globalPos.y || eventPoint.position.y > globalPos.y + addressBar.height) {
                addressBar.isEditing = false
            }
        }
    }
}
