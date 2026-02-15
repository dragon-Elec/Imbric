import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

TabButton {
    id: control

    // Compact Padding (Nemo-style)
    // Compact Padding (Nemo-style)
    topPadding: 3
    bottomPadding: 4
    leftPadding: 4
    rightPadding: 4

    // Access System Palette
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }

    // Signals
    signal closeClicked()

    // 1. Elastic Layout handled by parent TabBar automatically.
    Layout.fillWidth: true
    
    // 2. Composite Content Item
    contentItem: RowLayout {
        spacing: 4
        
        // Label takes available space
        Label {
            text: control.text
            font: control.font
            // Color: Active/Hover -> Bright Text, Inactive -> Dimmed Text
            color: (control.checked || control.hovered) ? sysPalette.text : Qt.alpha(sysPalette.text, 0.7)
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.leftMargin: 8
            verticalAlignment: Text.AlignVCenter
        }

        // Close Button (Native ToolButton)
        ToolButton {
            id: closeBtn
            text: "×" 
            // Accessible close icon if theme has it, else text fallback
            icon.name: "window-close-symbolic"
            icon.color: closeBtn.hovered ? sysPalette.highlight : sysPalette.text
            
            // Layout
            Layout.preferredWidth: 26
            Layout.preferredHeight: 26
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 4

            // Visuals: Flat, only visible on hover/checked
            flat: true
            visible: control.hovered || control.checked
            
            // Logic
            onClicked: control.closeClicked()
            
            // Specific styling to match Adwaita small rounded button
            // Specific styling to match Adwaita small rounded button
            background: Rectangle {
                radius: 13 // circle
                color: closeBtn.hovered ? Qt.alpha(sysPalette.highlight, 0.2) : "transparent"
                
                // Smooth Fade In/Out
                Behavior on color { ColorAnimation { duration: 200 } }
            }
        }
    }

    // 3. Background (Active State & Hover)
    background: Rectangle {
        // Active: Slightly lighter than window (or darker depending on theme)
        // Hover: Faint overlay
        readonly property color activeColor: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark ? 
                                           Qt.lighter(sysPalette.window, 1.2) : 
                                           Qt.darker(sysPalette.window, 1.1)
        
        color: control.checked ? activeColor : (control.hovered ? Qt.alpha(sysPalette.text, 0.05) : "transparent")
        
        // Zorin/Nemo style: Rounded top, square bottom
        radius: 6
        
        // Mask bottom corners if active (connection look)
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 6
            color: parent.color
            visible: control.checked
            radius: 0
        }
    }

    // 4. Separator
    Rectangle {
        width: 1
        height: parent.height * 0.5
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        color: sysPalette.mid // System separator color
        
        property int selectedIndex: control.TabBar.tabBar ? control.TabBar.tabBar.currentIndex : -1
        visible: !control.checked && !control.hovered 
                 && (index < control.TabBar.tabBar.count - 1) 
                 && (index + 1 !== selectedIndex)
        z: 1 
    }
}
