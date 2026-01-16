import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

Item {
    id: root
    
    // We get the list of models from Python: columnSplitter.getModels()
    property var columnModels: columnSplitter.getModels()
    property int columnCount: columnModels ? columnModels.length : 0
    // Calculate column width based on available space
    property real columnWidth: root.width > 0 ? (root.width - 40 - (columnCount - 1) * 10) / Math.max(columnCount, 1) : 200

    // --- 1. SMART MATERIAL SETUP ---
    // Inherit System Fonts and Colors for a native look
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }
    
    // Detect Dark Mode
    readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.Dark

    // Bind Material Theme to System Palette
    Material.theme: isSystemDark ? Material.Dark : Material.Light
    Material.accent: activePalette.highlight
    Material.primary: activePalette.highlight
    Material.background: activePalette.window
    Material.foreground: activePalette.text
        


    // Background Rectangle using Material Background
    Rectangle {
        anchors.fill: parent
        color: Material.background
    
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
                            
                            // Calculate Image Height (Aspect Ratio)
                            readonly property real imgHeight: {
                                if (model.isDir) return columnListView.width * 0.8
                                if (model.width > 0 && model.height > 0) {
                                    return (model.height / model.width) * columnListView.width
                                }
                                return columnListView.width
                            }
                            
                            // Footer Height for Text
                            readonly property int footerHeight: 36
                            
                            // Total Delegate Height
                            height: imgHeight + footerHeight

                            // The "Card" Container
                            Rectangle {
                                id: clipContainer
                                anchors.fill: parent
                                anchors.margins: 4 // External spacing
                                radius: 8
                                color: "transparent" // Let hover handle background
                                clip: true
                                
                                // 1. Main Image (Top)
                                Image {
                                    id: thumbnailImage
                                    width: parent.width
                                    height: delegateItem.imgHeight
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    
                                    source: "image://thumbnail/" + model.path
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: true
                                    
                                    onStatusChanged: {
                                        if (status === Image.Error) console.error("Image Load Error:", source)
                                    }
                                }
                                
                                // 2. Text Footer (Bottom) - No Gradient, Native Look
                                Rectangle {
                                    id: titleFooter
                                    width: parent.width
                                    height: delegateItem.footerHeight
                                    anchors.bottom: parent.bottom
                                    color: "transparent" // Clean look
                                    
                                    Text {
                                        anchors.centerIn: parent
                                        width: parent.width - 16
                                        
                                        text: model.name
                                        
                                        // Use System Colors (Smart Material)
                                        color: Material.foreground
                                        
                                        font.pixelSize: 12
                                        font.family: Qt.application.font.family
                                        elide: Text.ElideMiddle // Filename style
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                }
                                
                                // Hover Effect (Whole Card)
                                Rectangle {
                                    id: hoverBg
                                    anchors.fill: parent
                                    color: Material.foreground
                                    opacity: 0.0
                                    z: -1 // Behind content? No, container is transparent.
                                    // Actually, put it behind image? 
                                    // If we want hover to show a card background:
                                }
                                
                                states: [
                                    State {
                                        name: "hovered"
                                        when: mouseArea.containsMouse
                                        PropertyChanges { target: clipContainer; color: Qt.rgba(Material.foreground.r, Material.foreground.g, Material.foreground.b, 0.05) }
                                    }
                                ]
                                
                                // Hover & Click Interactions
                                MouseArea {
                                    id: mouseArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: model.isDir ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    
                                    onClicked: {
                                        if (model.isDir) {
                                            appBridge.openPath(model.path)
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
    
    // Zoom Logic (Ctrl + Scroll) - MouseArea Overlay
    MouseArea {
        anchors.fill: parent
        propagateComposedEvents: true // Let clicks pass through
        acceptedButtons: Qt.NoButton // Don't eat clicks/right-clicks
        hoverEnabled: true // Required for wheel events? actually onWheel works without this usually, but safe to add
        
        onWheel: (wheel) => {
            // Check for Ctrl Modifier
            if (wheel.modifiers & Qt.ControlModifier) {
                
                if (wheel.angleDelta.y > 0) {
                    // Zoom In
                    if (root.columnCount > 1) columnSplitter.setColumnCount(root.columnCount - 1)
                } else if (wheel.angleDelta.y < 0) {
                    // Zoom Out
                    if (root.columnCount < 8) columnSplitter.setColumnCount(root.columnCount + 1)
                }
                
                // Consume the event so ScrollView doesn't scroll
                wheel.accepted = true
            } else {
                // Pass event to underlying ScrollView
                wheel.accepted = false
            }
        }
    }
}
