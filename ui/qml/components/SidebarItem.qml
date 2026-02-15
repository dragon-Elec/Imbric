import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material

ItemDelegate {
    id: control

    // API
    property string textLabel: ""
    property string iconSymbol: ""
    property var usageData: null // { total: number, used: number, free: number }
    property bool isActive: false
    property bool showMountIndicator: false
    
    // Allow injecting custom widgets (e.g. Eject Button, Spinner)
    default property alias content: extensionArea.data

    // Styling Defaults
    width: ListView.view ? ListView.view.width - 16 : parent.width
    height: 40
    
    // "Qeesy" Press Effect
    scale: control.down ? 0.98 : 1.0
    Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } }

    background: Rectangle {
        radius: 8
        color: control.isActive ? Qt.rgba(Material.accent.r, Material.accent.g, Material.accent.b, 0.15) : 
               control.hovered ? Qt.rgba(Material.foreground.r, Material.foreground.g, Material.foreground.b, 0.05) : "transparent"
        
        // Subtle border for active state
        border.color: control.isActive ? Qt.rgba(Material.accent.r, Material.accent.g, Material.accent.b, 0.3) : "transparent"
        border.width: 1
        
        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }

    contentItem: RowLayout {
        spacing: 12
        
        // Icon Container
        Item {
            Layout.preferredWidth: 24
            Layout.preferredHeight: 24
            Layout.alignment: Qt.AlignVCenter
            
            Label {
                anchors.centerIn: parent
                text: control.iconSymbol
                font.pixelSize: 18
                color: control.isActive ? Material.accent : Material.foreground
                Behavior on color { ColorAnimation { duration: 150 } }
            }
        }

        // Main Label Area
        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2

            Label {
                text: control.textLabel
                Layout.fillWidth: true
                elide: Text.ElideRight
                color: Material.foreground
                font.bold: control.isActive
                font.pixelSize: 14
            }

            // Usage Bar (Only if usageData is present)
            Rectangle {
                visible: control.usageData !== null && control.usageData.total > 0
                Layout.fillWidth: true
                Layout.preferredHeight: 3
                radius: 1.5
                color: Qt.rgba(Material.foreground.r, Material.foreground.g, Material.foreground.b, 0.1)
                
                Rectangle {
                    width: parent.width * ((control.usageData && control.usageData.total > 0) ? (control.usageData.used / control.usageData.total) : 0)
                    height: parent.height
                    radius: 1.5
                    color: {
                        var ratio = (control.usageData && control.usageData.total > 0) ? (control.usageData.used / control.usageData.total) : 0
                        if (ratio > 0.9) return "#F44336" // Red if full
                        if (ratio > 0.75) return "#FF9800" // Orange if getting full
                        return Material.accent // Default accent
                    }
                    Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                    Behavior on color { ColorAnimation { duration: 300 } }
                }
            }
        }

        // Scalable Extension Area (Right Side)
        // This is where extra widgets (Spinner, Eject Button) will go
        RowLayout {
            id: extensionArea
            Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
            spacing: 8
        }

        // Default Mount Indicator (Only if no custom content)
        Rectangle {
            visible: control.showMountIndicator && extensionArea.children.length === 0
            width: 6; height: 6; radius: 3
            color: Material.accent
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 8
        }
    }
    
    // ToolTip helper
    ToolTip {
        visible: control.hovered && !control.down
        text: control.textLabel
        delay: 800
    }
}
