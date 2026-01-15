import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1200
    height: 800
    title: qsTr("Imbric")
    // Native System Palette - respects GTK Theme (Light/Dark)
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // Use system window color (prevents resizing jitter)
    color: activePalette.window

    SplitView {
        anchors.fill: parent
        
        // Sidebar
        Rectangle {
            SplitView.preferredWidth: 250
            SplitView.minimumWidth: 150
            SplitView.maximumWidth: 400
            
            // Sidebar background
            color: activePalette.base
            
            ListView {
                anchors.fill: parent
                model: sidebarModel
                clip: true // Important for resizing performance
                
                delegate: ItemDelegate {
                    width: parent.width
                    
                    text: model.name
                    icon.name: model.icon 
                    icon.color: "transparent" // Ensure we see original colors if applicable, or binding usually handles it
                    
                    // Force palette binding for proper colors
                    palette.text: activePalette.text
                    palette.windowText: activePalette.text
                    palette.highlight: activePalette.highlight
                    palette.highlightedText: activePalette.highlightedText
                    
                    highlighted: ListView.isCurrentItem
                    
                    onClicked: {
                        console.log("Clicked: " + model.path)
                        appBridge.openPath(model.path)
                    }
                }
            }
        }

        // Main Content Area
        ColumnLayout {
            SplitView.fillWidth: true
            spacing: 0
            
            // Breadcrumb Bar
            Loader {
                id: breadcrumbLoader
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                source: "components/BreadcrumbBar.qml"
                
                // Bindings
                Binding {
                    target: breadcrumbLoader.item
                    property: "currentPath"
                    value: window.currentPath
                }
                
                Connections {
                    target: breadcrumbLoader.item
                    function onNavigateTo(path) {
                        appBridge.openPath(path)
                    }
                }
            }
            
            // Main View
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: activePalette.window
                
                Loader {
                    id: viewLoader
                    anchors.fill: parent
                    source: "views/MasonryView.qml" 
                }
            }
        }
    }
    
    property string currentPath: "/"
    
    Connections {
        target: appBridge
        function onPathChanged(newPath) {
            window.currentPath = newPath
        }
    }
}
