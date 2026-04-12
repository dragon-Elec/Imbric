import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material

Item {
    id: root
    
    // --- PUBLIC API ---
    property string text: ""
    property string icon: "" 
    property bool collapsed: false
    default property alias controls: controlSlot.data
    
    signal toggleCollapsed()
    
    // --- INTERNAL STATE ---
    // --- HOVER & EXPANSION LOGIC ---

    // 1. Detect Mouse Presence anywhere in the component (non-blocking)
    HoverHandler {
        id: hoverHandler
    }

    // 2. Debounce Timers (Hysteresis)
    // Prevents flicker when mouse briefly leaves or interacts with child controls
    Timer {
        id: collapseTimer
        interval: 180 // ms delay before collapsing (Snappier)
        repeat: false
        onTriggered: root.internalHovered = false
    }

    // Prevents accidental expansion when passing over
    Timer {
        id: dwellTimer
        interval: 300 // ms delay before expanding (Safe)
        repeat: false
        onTriggered: root.internalHovered = true
    }

    // 3. Processed Hover State
    property bool internalHovered: false
    
    // Logic: Updates internal state based on HoverHandler + Timer
    Connections {
        target: hoverHandler
        function onHoveredChanged() {
            if (hoverHandler.hovered) {
                collapseTimer.stop()
                dwellTimer.start()
            } else {
                dwellTimer.stop()
                collapseTimer.start()
            }
        }
    }
    
    // Show controls ONLY if internally hovered AND not collapsed AND controls exist
    property bool hasControls: false
    property bool showControls: internalHovered && !collapsed && hasControls

    // --- HEIGHT LOGIC ---
    property int compactHeight: 32
    property int expandedHeight: compactHeight + controlRow.implicitHeight + 4

    implicitHeight: showControls ? expandedHeight : compactHeight
    implicitWidth: parent.width

    // Smooth Height Animation
    Behavior on implicitHeight { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

    // Background (Tab-like appearance)
    Rectangle {
        anchors.fill: parent
        // Base color slightly darker/lighter than window to distinguish as header
        color: root.internalHovered ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.08) : 
               Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.03)
        
        radius: 6
        border.color: root.internalHovered ? Qt.rgba(sysPalette.text.r, sysPalette.text.g, sysPalette.text.b, 0.1) : "transparent"
        border.width: 1

        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 4 // General padding
        spacing: 0
        
        // --- ROW 1: Label & Collapse Toggle ---
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 24 // compact height minus margins
            
            // Handle Taps ONLY on the header row
            TapHandler {
                id: tapHandler
                onTapped: {
                    root.collapsed = !root.collapsed
                    root.toggleCollapsed()
                }
            }

            RowLayout {
                anchors.fill: parent
                spacing: 8
                
                // Arrow Icon
                Label {
                    text: root.collapsed ? "▸" : "▾"
                    font.pointSize: 10 // roughly 12px
                    color: Material.foreground
                    opacity: 0.6
                    Layout.alignment: Qt.AlignVCenter
                }
                
                // Section Icon (Optional)
                Label {
                    visible: root.icon !== ""
                    text: root.icon
                    font.pixelSize: 14 // Keep icons pixel-perfect
                    color: Material.foreground
                    opacity: 0.7
                    Layout.alignment: Qt.AlignVCenter
                }

                // Label Text
                Label {
                    text: root.text
                    font.pointSize: 9 // roughly 11px
                    font.bold: true
                    font.capitalization: Font.AllUppercase
                    color: Material.foreground
                    opacity: 0.6
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                }
            }
        }
        
        // --- ROW 2: Control Tray ---
        RowLayout {
            id: controlRow
            Layout.fillWidth: true
            
            // Visibility Logic
            visible: root.showControls // Layout visibility 
            opacity: root.showControls ? 1.0 : 0.0
            
            Layout.alignment: Qt.AlignRight
            
            // Spacer to push controls to right
            Item { Layout.fillWidth: true }
            
            RowLayout {
                id: controlSlot
                spacing: 4
                Layout.alignment: Qt.AlignRight
            }
            
            // Fade In/Out Animation
            Behavior on opacity { NumberAnimation { duration: 150 } }
        }
        
        // Spacer to enforce Top Alignment during height animation
        Item { Layout.fillHeight: true }
    }

    Component.onCompleted: {
        // Removed auto-detection to allow explicit binding
    }
}
