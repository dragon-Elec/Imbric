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

    // Bridge Properties (set from Python)
    property var quickAccessModel: [] 
    property var volumesModel: []
    
    // Internal State
    property string currentSelection: "Home"

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
        // Logic to highlight item based on path
        // 1. Check Quick Access
        for (var i = 0; i < quickAccessModel.length; i++) {
            if (quickAccessModel[i].path === path) {
                currentSelection = quickAccessModel[i].name
                return
            }
        }
        // 2. Check Volumes
        for (var j = 0; j < volumesModel.length; j++) {
             if (volumesModel[j].path === path) {
                currentSelection = volumesModel[j].name
                return
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 1. QUICK ACCESS GRID
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: flowLayout.height + 24
            Layout.topMargin: 12
            
            Flickable {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                contentHeight: flowLayout.height
                clip: true
                interactive: false

                Flow {
                    id: flowLayout
                    width: parent.width
                    spacing: 4
                    
                    // SMOOTH REFLOW ANIMATION (Restored)
                    move: Transition {
                        NumberAnimation { properties: "x,y"; duration: 300; easing.type: Easing.OutCubic }
                    }
                    
                    add: Transition {
                        NumberAnimation { properties: "scale"; from: 0.9; to: 1.0; duration: 200; easing.type: Easing.OutQuad }
                        NumberAnimation { properties: "opacity"; from: 0.0; to: 1.0; duration: 200 }
                    }
                    
                    Repeater {
                        model: root.quickAccessModel
                        delegate: ItemDelegate {
                            id: gridDelegate
                            width: 60; height: 60; padding: 0
                            
                            property var itemData: modelData
                            property bool isSelected: root.currentSelection === (itemData ? itemData.name : "")
                            
                            // "Qeesy" Press Effect
                            scale: gridDelegate.down ? 0.96 : 1.0
                            Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }
                            
                                background: Rectangle {
                                    radius: 12
                                    color: isSelected ? Qt.rgba(sysPalette.highlight.r, sysPalette.highlight.g, sysPalette.highlight.b, 0.15) : 
                                           parent.hovered ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.05) : "transparent"
                                    
                                    // Persistent subtle outline for non-active items
                                    border.color: (isSelected || parent.hovered) ? sysPalette.highlight : Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.15)
                                    border.width: isSelected ? 2 : 1
                                    
                                    Behavior on color { ColorAnimation { duration: 150 } }
                                    Behavior on border.color { ColorAnimation { duration: 150 } }
                                }

                            contentItem: Column {
                                anchors.centerIn: parent
                                spacing: 2
                                Label {
                                    text: (itemData && itemData.icon) ? root.getIconChar(itemData.icon) : "?"
                                    // Custom Size Overrides
                                    property int baseSize: (itemData && (itemData.icon === "description" || itemData.icon === "history")) ? 26 : 22
                                    font.pixelSize: baseSize 
                                    
                                    color: isSelected ? sysPalette.highlight : sysPalette.text
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    Behavior on color { ColorAnimation { duration: 150 } }
                                }
                                Label {
                                    text: (itemData && itemData.name) ? itemData.name : ""
                                    font.pixelSize: 9
                                    color: sysPalette.text
                                    opacity: isSelected ? 1.0 : 0.7
                                    font.bold: isSelected
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    visible: width < parent.width 
                                    elide: Text.ElideRight
                                }
                            }
                            onClicked: {
                                if (itemData) {
                                    root.currentSelection = itemData.name
                                    root.navigationRequested(itemData.path)
                                }
                            }
                            ToolTip {
                                id: gridToolTip
                                visible: parent.hovered
                                text: (itemData && itemData.name) ? itemData.name : ""
                                delay: 500
                                background: Rectangle {
                                    color: sysPalette.window
                                    border.color: sysPalette.mid
                                    radius: 4
                                }
                                contentItem: Text {
                                    text: gridToolTip.text
                                    color: sysPalette.text
                                }
                            }
                        }
                    }
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 1
            color: sysPalette.midlight; opacity: 0.3
            Layout.margins: 12
        }

        // 2. VOLUMES LIST
        ListView {
            id: volumesList
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            topMargin: 8
            spacing: 2
            model: root.volumesModel
            
            delegate: SidebarItem {
                id: listItem
                width: ListView.view.width - 16
                anchors.horizontalCenter: parent.horizontalCenter
                
                property var itemData: modelData
                
                textLabel: (itemData && itemData.name) ? itemData.name : ""
                iconSymbol: (itemData && itemData.icon) ? root.getIconChar(itemData.icon) : "?"
                usageData: (itemData && itemData.usage) ? itemData.usage : null
                isActive: root.currentSelection === (itemData ? itemData.name : "")
                showMountIndicator: itemData ? (itemData.isMounted === true) : false
                
                // Add Unmount Button for mounted drives
                ToolButton {
                    visible: (itemData && itemData.isMounted && itemData.canUnmount)
                    text: "⏏" // Eject Symbol
                    font.pixelSize: 14
                    flat: true
                    opacity: hovered ? 1.0 : 0.6
                    
                    background: Rectangle {
                        color: parent.down ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.1) : "transparent"
                        radius: 4
                    }
                    
                    onClicked: {
                        if (itemData) {
                            root.unmountRequested(itemData.identifier)
                        }
                    }
                }

                onClicked: {
                    if (itemData) {
                        root.currentSelection = itemData.name
                        if (itemData.isMounted) {
                            if (itemData.path) {
                                root.navigationRequested(itemData.path)
                            }
                        } else {
                            // Request Mount
                            root.mountRequested(itemData.identifier)
                        }
                    }
                }
            }
        }
    }
}
