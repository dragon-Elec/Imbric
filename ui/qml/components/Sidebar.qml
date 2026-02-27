import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material

Pane {
    id: root
    padding: 0
    background: Rectangle { color: sysPalette.window }

    // Signals
    signal navigationRequested(string path)
    signal mountRequested(string identifier)
    signal unmountRequested(string identifier)
    signal sectionActionTriggered(string sectionTitle, string action)
    signal sectionToggled(string sectionTitle, bool collapsed)

    // Bridge Properties (set from Python context)
    // The core model is 'sidebarModel', injected as 'sectionsModel' property here.
    property var sectionsModel
    
    // Internal State
    property string currentSelectionPath: ""
    
    // --- SYSTEM PALETTE ---
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }
    readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    
    // Bind Material Theme to System
    Material.theme: isSystemDark ? Material.Dark : Material.Light
    Material.accent: sysPalette.highlight

    // --- HELPER FUNCTIONS ---
    function getIconChar(name) {
        switch(name) {
            case "history": return "◴"       // Recent
            case "star": return "★"         // Starred
            case "home": return "⌂"         // Home
            case "description": return "🗎"  // Documents
            case "file_download": return "➜]" // Downloads
            case "image": return "[◉¯]"     // Pictures
            case "delete": return "🗑"      // Trash Empty
            case "delete_full": return "🗑⃨!" // Trash Full
            case "hard_drive": return "🖴"   // HDD
            case "ssd": return "𓈙"          // SSD
            case "music_note": return "𝄞"    // Music
            case "movie": return "[ ▶︎ ]"    // Videos
            case "desktop_windows": return "﹒ ⃣ " // Desktop
            case "drive-harddisk": return "🖴" // HDD
            case "drive-harddisk-solidstate": return "𓈙" // SSD
            case "drive-harddisk-system": return "🖴" // System Drive
            case "drive-solid-state": return "𓈙" // SSD
            case "folder": return "🗀"       // Generic Folder
            case "tag": return "🏷"         // Generic Bookmark
            case "network": return "🖧"      // Network
            case "network-server": return "🖧"
            case "network-workgroup": return "🖧"
            case "folder-remote": return "🖧" // Network Folder
            case "folder-network": return "🖧" // Network Folder
            case "usb": return "♆"          // USB
            case "drive-removable-media": return "♆"
            case "media-removable": return "♆"
            case "phone": return "📱"       // Phone
            case "smartphone": return "📱"
            case "multimedia-player": return "📻" // Media Player
            case "camera-photo": return "📷" // Camera
            case "camera": return "📷"
            case "media-optical": return "◎" // Optical
            case "drive-optical": return "◎"
            case "root": return "</>"        // Root
            default: return "○"
        }
    }

    function syncToPath(path) {
        // Because we are using QAbstractListModel now, scanning through it manually
        // from QML is slightly harder than JS Arrays. For now, we wait for a click.
        // Full programmatic selection sync can be implemented via a proper SelectionModel later.
        currentSelectionPath = path
    }

    ScrollView {
        id: sidebarScroll
        anchors.fill: parent
        // Prevent horizontal scrolling by binding contentWidth
        contentWidth: availableWidth
        
        // Use custom GTK ScrollBar (overlay, auto-hiding, self-contained)
        ScrollBar.vertical: GtkScrollBar {
            id: sidebarScrollBar
            // Explicitly anchor to fill vertical space and stick to right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            
            // Optional: Enable pillar/track if desired (TRUE for testing)
            showTrack: true 
            
            // Disable Physics Engine (using native ScrollView behavior)
            physicsEnabled: false
            turboMode: false
        }
        
        property real pushOffset: sidebarScrollBar.active ? (sidebarScrollBar.width + 2) : 0
        Behavior on pushOffset { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        
        Column {
            // Layout Stability Fix:
            // The Main Column stays FULL WIDTH. We selectively shrink children (Header/Lists) 
            // but let Grids overlap the scrollbar area to prevent reflow loops.
            width: parent.width
            spacing: 0

            Repeater {
                model: root.sectionsModel
                delegate: Column {
                    id: sectionDelegate
                    width: parent.width
                    spacing: 0
                    
                    // PERFORMANCE: Layer disabled to prevent text blur
                    // layer.enabled: true
                    // layer.smooth: true
                    
                    property var sectionData: modelData

                    SidebarHeader {
                        id: header
                        // Headers have buttons on the right, so they MUST shrink/push
                        width: parent.width - sidebarScroll.pushOffset
                        
                        // To avoid QML context confusion in the inner Repeater, explicitly define property
                        property var actionsList: model.actions !== undefined ? model.actions : []
                        
                        text: model.title !== undefined ? model.title : ""
                        icon: root.getIconChar(model.icon !== undefined ? model.icon : "")
                        collapsed: model.collapsed !== undefined ? model.collapsed : false
                        hasControls: model.actions !== undefined && model.actions.length > 0
                        
                        onToggleCollapsed: {
                            // Notify parent to update state persistence
                            root.sectionToggled(model.title, header.collapsed)
                        }
                        
                        // Dynamic Header Actions
                        Repeater {
                            model: header.actionsList
                            delegate: ToolButton {
                                text: modelData === "Add" ? "+" : (modelData === "Refresh" ? "⟳" : (modelData === "Settings" ? "⚙" : "?"))
                                font.pointSize: 10 // roughly 14px
                                flat: true
                                opacity: hovered ? 1.0 : 0.6
                                // Use the explicitly named title from the outer context
                                onClicked: root.sectionActionTriggered(header.text, modelData)
                                background: Rectangle { color: parent.down ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.1) : "transparent"; radius: 4 }
                            }
                        }
                    }

                    Loader {
                        visible: !header.collapsed
                        
                        // Lists need to push (avoid deadzone). Grids handle overlap (stable layout).
                        width: model.type === "GRID" ? parent.width : (parent.width - sidebarScroll.pushOffset)
                        
                        // Shrink-wrap: Use implicit height of the loaded item (Grid or List)
                        height: item ? item.implicitHeight : 0

                        sourceComponent: model.type === "GRID" ? gridComponent : (model.type === "LIST" ? listComponent : null)
                        
                        // THIS IS THE MAGIC - Bind to the inner ItemsModel directly!
                        property var dataModel: model.itemsModel
                    }
                }
            }
            
            // Filler to push content up if needed? 
            // In a ScrollView, we generally don't need a filler to push things up, 
            // but if we want the background to be solid, it's fine. 
            // Actually, remove the filler to let it properly shrink-wrap.
        }
    }

    // --- COMPONENT DEFINITIONS ---

    Component {
        id: gridComponent
        
        Item {
            // Grid always takes the full allocated width from the Loader
            width: parent ? parent.width : 0
            // Loader needs implicitHeight for Layout to work in ColumnLayout
            implicitHeight: flowLayout.height + 12
            
            Flickable {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                contentHeight: flowLayout.height
                clip: true
                interactive: false // Assuming grid is small enough or handled by outer scroll? Actually sidebar usually doesn't scroll whole thing.
                // If the grid grows huge, we might need a ScrollView. For now, strict 'Fit'
                
                Flow {
                    id: flowLayout
                    width: parent.width
                    spacing: 4

                    move: Transition {
                        NumberAnimation { properties: "x,y"; duration: 300; easing.type: Easing.OutCubic }
                    }
                    
                    Repeater {
                        model: dataModel // injected by Loader
                        delegate: ItemDelegate {
                            id: gridDelegate
                            width: 60; height: 60; padding: 0
                            
                            property string itemPath: model.path !== undefined ? model.path : ""
                            property bool isSelected: root.currentSelectionPath !== "" && root.currentSelectionPath === itemPath
                            
                            scale: gridDelegate.down ? 0.96 : 1.0
                            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }
                            
                            background: Rectangle {
                                radius: 12
                                color: isSelected ? Qt.rgba(sysPalette.highlight.r, sysPalette.highlight.g, sysPalette.highlight.b, 0.15) : 
                                       parent.hovered ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.05) : "transparent"
                                border.color: (isSelected || parent.hovered) ? sysPalette.highlight : Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.15)
                                border.width: isSelected ? 2 : 1
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Behavior on border.color { ColorAnimation { duration: 150 } }
                            }

                            contentItem: Column {
                                anchors.centerIn: parent
                                spacing: 2
                                Label {
                                    text: model.icon !== undefined ? root.getIconChar(model.icon) : "?"
                                    font.pixelSize: (model.icon === "description" || model.icon === "history") ? 26 : 22 // Keep icons pixel-based
                                    color: isSelected ? sysPalette.highlight : sysPalette.text
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                Label {
                                    text: model.name !== undefined ? model.name : ""
                                    font.pointSize: 7 // roughly 9px
                                    color: sysPalette.text
                                    opacity: isSelected ? 1.0 : 0.7
                                    font.bold: isSelected
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    visible: width < parent.width 
                                    elide: Text.ElideRight
                                }
                            }
                            onClicked: {
                                if (model.path) {
                                    root.currentSelectionPath = model.path
                                    root.navigationRequested(model.path)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: listComponent
        
        ListView {
            // Ensure width fills the loader
            width: parent ? parent.width : 0
            // Shrink-wrap: Set height to contentHeight PLUS topMargin to prevent clipping
            implicitHeight: contentHeight + topMargin
            interactive: false // ScrollView handles scrolling
            
            clip: true
            topMargin: 8
            spacing: 2
            model: dataModel // injected by Loader
            
            delegate: SidebarItem {
                width: ListView.view.width - 16
                anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
                
                textLabel: model.name !== undefined ? model.name : ""
                iconSymbol: model.icon !== undefined ? root.getIconChar(model.icon) : "?"
                usageData: model.usage !== undefined ? model.usage : null
                isActive: root.currentSelectionPath !== "" && root.currentSelectionPath === model.path
                showMountIndicator: model.isMounted !== undefined ? model.isMounted : false
                
                ToolButton {
                    visible: (model.isMounted !== undefined && model.isMounted === true && model.canUnmount !== undefined && model.canUnmount === true)
                    text: "⏏"
                    font.pointSize: 10 // roughly 14px
                    flat: true
                    opacity: hovered ? 1.0 : 0.6
                    background: Rectangle { color: parent.down ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.1) : "transparent"; radius: 4 }
                    onClicked: {
                        if (model.identifier !== undefined) root.unmountRequested(model.identifier)
                    }
                }

                onClicked: {
                    if (model.path !== undefined) {
                        root.currentSelectionPath = model.path
                        if (model.isMounted !== undefined && model.isMounted) {
                            if (model.path) root.navigationRequested(model.path)
                        } else {
                            if (model.identifier !== undefined) {
                                root.mountRequested(model.identifier)
                                // Restored behavior: still fire navigation so UI jumps there after mount
                                if (model.path) root.navigationRequested(model.path)
                            }
                        }
                    }
                }
            }
        }
    }
}
