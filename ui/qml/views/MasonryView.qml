import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    
    // We get the list of models from Python: columnSplitter.getModels()
    property var columnModels: columnSplitter.getModels()
    property int columnCount: columnModels ? columnModels.length : 0
    // Calculate column width based on available space
    property real columnWidth: root.width > 0 ? (root.width - 40 - (columnCount - 1) * 10) / Math.max(columnCount, 1) : 200

    // Access System Palette
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }
    
    // Background Rectangle using System Window Color
    Rectangle {
        anchors.fill: parent
        color: activePalette.window
    
        ScrollView {
            id: scrollView
            anchors.fill: parent
            clip: true
            
            // Horizontal Row of Columns
            Row {
                id: columnsRow
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 10
                
                // Generate N columns
                Repeater {
                    id: columnRepeater
                    model: root.columnModels
                    
                    delegate: ListView {
                        id: columnListView
                        // Use explicit column width calculated from root
                        width: root.columnWidth
                        
                        interactive: false // Let parent ScrollView handle inputs
                        height: contentHeight // Expand to fit all items
                        
                        model: modelData // The SimpleListModel for this column
                        
                        delegate: Item {
                            id: delegateItem
                            width: columnListView.width
                            // Calculate exact height based on aspect ratio
                            // Fallback to square (width) if no dimensions or isDir
                            height: {
                                if (model.isDir) return columnListView.width * 0.8 // Slightly shorter for folders
                                if (model.width > 0 && model.height > 0) {
                                    return (model.height / model.width) * columnListView.width
                                }
                                return columnListView.width // Square fallback
                            } 
                            
                            Image {
                                id: thumbnailImage
                                anchors.fill: parent
                                anchors.margins: 5
                                source: "image://thumbnail/" + model.path
                                
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                cache: true
                                
                                onStatusChanged: {
                                    if (status === Image.Error) {
                                        console.error("Image Load Error:", source)
                                    }
                                }
                                
                                // Visual frame
                                Rectangle {
                                    anchors.fill: parent
                                    color: "transparent"
                                    border.color: "#33ffffff"
                                    border.width: 1
                                    radius: 4
                                }
                                
                                // Filename overlay
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 20
                                    color: "#80000000"
                                    
                                    Text {
                                        anchors.centerIn: parent
                                        text: model.name
                                        color: "white"
                                        font.pixelSize: 10
                                        elide: Text.ElideRight
                                        width: parent.width - 4
                                    }
                                }
                                
                                // Navigation MouseArea
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: model.isDir ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    
                                    onClicked: {
                                        if (model.isDir) {
                                            console.log("Navigating to:", model.path)
                                            appBridge.openPath(model.path)
                                        } else {
                                            console.log("Clicked file:", model.path)
                                            // TODO: Open file preview
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    // Auto-refresh when Python signals change
    Connections {
        target: columnSplitter
        function onColumnsChanged() {
            root.columnModels = columnSplitter.getModels()
        }
    }
}
