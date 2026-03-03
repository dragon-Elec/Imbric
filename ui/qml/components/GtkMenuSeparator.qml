import QtQuick
import QtQuick.Controls

// A reusable pure GTK mimic for the separator
MenuSeparator {
    id: root
    padding: 0
    topPadding: 4
    bottomPadding: 4
    
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }
    
    contentItem: Rectangle {
        // Separators should not dictate the width of the menu.
        implicitWidth: 0
        implicitHeight: 1
        
        // Use a more visible separator color based on the theme
        color: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark ? "#383838" : "#d0d0d0"
        
        // GTK menus keep padding on the edges of separators
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 12
        anchors.rightMargin: 12
    }
}
