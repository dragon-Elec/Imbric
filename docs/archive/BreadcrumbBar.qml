import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    height: 40
    color: activePalette.window
    
    // Props
    property string currentPath: "" 
    
    // Signal for navigation
    signal navigateTo(string path)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 2

        // "Up" Button
        Button {
            icon.name: "go-up"
            flat: true
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            
            onClicked: {
                if (!root.currentPath || root.currentPath === "/") return;
                
                // Simple string manipulation to go up
                // Remove trailing slash
                var path = root.currentPath
                if (path.endsWith("/")) path = path.slice(0, -1)
                
                var lastSlash = path.lastIndexOf("/")
                if (lastSlash > 0) {
                    var parentPath = path.substring(0, lastSlash)
                    root.navigateTo(parentPath)
                } else {
                    root.navigateTo("/")
                }
            }
        }

        // Path Text Field (editable in future, for now just text)
        TextField {
            text: root.currentPath
            Layout.fillWidth: true
            readOnly: true
            selectByMouse: true
            
            background: Rectangle {
                color: activePalette.base
                border.color: activePalette.mid
                radius: 4
            }
        }
    }
}
