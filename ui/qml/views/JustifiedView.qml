import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import components as Components

/**
 * JustifiedView — Simple row-based grid using native Qt elements
 * 
 * Architecture:
 * - ListView for rows (vertical scrolling)
 * - RowDelegate for each row (horizontal layout)
 * - FileDelegate for each item (handles its own clicks)
 * - Background MouseArea for clear-selection only
 */
Item {
    id: root
    
    // =========================================================================
    // 1. DATA BINDING FROM PYTHON
    // =========================================================================
    required property var rowBuilder
    required property var tabController
    property var rows: []
    
    Connections {
        target: rowBuilder
        function onRowsChanged() { 
            root.rows = rowBuilder.getRows() 
        }
        function onSelectAllRequested() {
            root.selectAll()
        }
    }
    
    Component.onCompleted: {
        if (rowBuilder) {
            root.rows = rowBuilder.getRows()
        }
    }

    property int rowHeight: 120
    
    Connections {
        target: rowBuilder
        function onRowHeightChanged(h) { root.rowHeight = h }
    }
    
    // =========================================================================
    // 2. SERVICES
    // =========================================================================
    required property var bridge
    
    // UNUSED but passed for consistency
    property var fileScanner
    
    // =========================================================================
    // 3. SELECTION STATE
    // =========================================================================
    property alias currentSelection: selectionModel.selection
    
    function selectPaths(paths) {
        selectionModel.selection = paths
    }

    function selectAll() {
        selectionModel.selectAll(rowBuilder.getAllItems())
    }
    
    // =========================================================================
    // 4. RENAME STATE
    // =========================================================================
    property string pathBeingRenamed: ""
    
    Connections {
        target: root.bridge
        function onRenameRequested(path) {
            root.pathBeingRenamed = path
        }
    }

    // =========================================================================
    // 5. COMPONENTS
    // =========================================================================
    Components.SelectionModel {
        id: selectionModel
        
        onSelectionChanged: {
            // Push selection update to backend
            if (tabController) {
                tabController.updateSelection(selection)
            }
        }
    }

    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // =========================================================================
    // 6. MAIN LAYOUT — Simple, No Z-Order Tricks
    // =========================================================================
    Rectangle {
        anchors.fill: parent
        // Documentation: https://doc.qt.io/qt-6/qstylehints.html#colorScheme-prop
        readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
        color: isSystemDark ? Qt.darker(activePalette.base, 1.3) : activePalette.base
        focus: true
        clip: true

        // 2. DropArea — External file drops
        DropArea {
            anchors.fill: parent
            onEntered: (drag) => {
                if (drag.modifiers & Qt.ControlModifier) {
                    drag.accept(Qt.CopyAction)
                } else {
                    drag.accept(Qt.MoveAction)
                }
            }
            onDropped: (drop) => {
                if (drop.hasUrls) {
                    var mode = "auto"
                    if (drop.action === Qt.CopyAction || (drop.modifiers & Qt.ControlModifier)) {
                        mode = "copy"
                    } else if (drop.action === Qt.MoveAction) {
                        mode = "move"
                    }

                    drop.accept()
                    var urls = []
                    for (var i = 0; i < drop.urls.length; i++) 
                        urls.push(drop.urls[i].toString())
                    root.bridge.handleDrop(urls, "", mode)
                }
            }
        }

        // 3. Background Actions
        TapHandler {
            acceptedButtons: Qt.LeftButton
            acceptedModifiers: Qt.KeyboardModifierMask
            onTapped: {
                selectionModel.clear()
                root.forceActiveFocus()
            }
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            acceptedModifiers: Qt.KeyboardModifierMask
            gesturePolicy: TapHandler.WithinBounds
            onTapped: {
                if (root.bridge) root.bridge.showBackgroundContextMenu()
            }
        }

        // =========================================================================
        // 7. BACKGROUND MESSAGE (Empty State / Error / Info)
        // =========================================================================
        property string messageText: ""
        property string messageIcon: ""

        Column {
            anchors.centerIn: parent
            spacing: 16
            opacity: 0.4
            visible: root.messageText !== ""
            z: 0

            Text {
                text: root.messageIcon || ""
                font.pixelSize: 64
                color: activePalette.text
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: root.messageText || ""
                font.pixelSize: 22
                font.bold: true
                color: activePalette.text
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }

        // 4. Main List View (Direct, no ScrollView wrapper)
        ListView {
            id: rowListView
            anchors.fill: parent
            // PADDING: Use internal margins instead of anchors to avoid clipping scrollbars/dead zones
            leftMargin: 12
            rightMargin: 18
            topMargin: 18
            bottomMargin: 12
            
            clip: true
            
            // Interaction:
            // - False: Disables native Flickable drag (fixes click conflict).
            // - True: We would lose empty-area clicks.
            interactive: false 

            // ScrollBar: Attached directly. 
            // "active: true" keeps it visible/fading correctly.
            // "interactive: true" ensures we can drag it even if ListView is interactive: false.
            // ScrollBar: Specialized GTK component with Turbo Boost
            ScrollBar.vertical: Components.GtkScrollBar {
                id: verticalScrollBar
                flickable: rowListView
                showTrack: true
                physicsEnabled: true // Enable internal physics engine
                turboMode: rowListView.turboMode
            }

            // Physics State
            property bool turboMode: true // Defaulted to true for testing

            // Proxy WheelHandler: Captures events on the View and forwards to ScrollBar logic
            WheelHandler {
                target: rowListView
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: (event) => verticalScrollBar.handleWheel(event)
            }


            // Native-like Smoothing
            // DISABLED when ScrollBar is pressed to allow instant 1:1 dragging.
            Behavior on contentY {
                enabled: !rowListView.interactive && !rowListView.ScrollBar.vertical.pressed
                NumberAnimation { 
                    duration: 200
                    easing.type: Easing.OutCubic
                }
            }
            
            model: root.rows
            spacing: 10
            
            header: Item { height: 10 }
            footer: Item { height: 10 }
            
            delegate: Components.RowDelegate {
                bridge: root.bridge
                selModel: selectionModel
                rowBuilder: root.rowBuilder // Pass down
                view: root
                imageHeight: root.rowHeight
                // x: 0 // Default (relative to contentItem which respects leftMargin)
            }

            onWidthChanged: {
                // Correctly inform Python of the ACTUAL available width for content
                if (rowBuilder) rowBuilder.setAvailableWidth(width - leftMargin - rightMargin)
            }
        }

        // 4. Marquee Selection Engine
        
        // Auto-Scroll Timer
        Timer {
            id: autoScrollTimer
            interval: 16 // 60 FPS
            repeat: true
            property int scrollSpeed: 0
            
            onTriggered: {
                // 1. Scroll
                var newY = rowListView.contentY + scrollSpeed
                
                // Clamp
                var minY = -rowListView.topMargin
                var maxY = Math.max(minY, rowListView.contentHeight - rowListView.height + rowListView.bottomMargin)
                newY = Math.max(minY, Math.min(newY, maxY))
                
                if (rowListView.contentY !== newY) {
                    rowListView.contentY = newY
                    // 2. Force Selection Update (since contentY changed, visual rect changes)
                    marqueeHandler.updateSelection()
                }
            }
        }

        DragHandler {
            id: marqueeHandler
            target: null 
            acceptedButtons: Qt.LeftButton
            
            // STATE: Persist Start Point in CONTENT SPACE to prevent drift
            property real startContentX: 0
            property real startContentY: 0
            property bool isSelecting: false
            
            onActiveChanged: {
                if (active) {
                    // START
                    isSelecting = true
                    var start = centroid.pressPosition
                    
                    // Capture Start in CONTENT SPACE
                    // Visual X (relative to Rectangle) -> Content X
                    // ListView has leftMargin (previously hardcoded 10+10). Now just LeftMargin.
                    startContentX = start.x - rowListView.leftMargin        
                    
                    // Visual Y (relative to Rectangle) -> Content Y
                    // ListView has topMargin. ContentY starts at -topMargin.
                    // Visual Y = topMargin + (Item Y - contentY) -> Item Y = Visual Y - topMargin + contentY
                    startContentY = start.y - rowListView.topMargin + rowListView.contentY
                    
                    rubberBand.show()
                    updateSelection()
                } else {
                    // FINISH
                    isSelecting = false
                    rubberBand.hide()
                    autoScrollTimer.stop()
                }
            }
            
            onCentroidChanged: {
                if (active) {
                    updateSelection()
                    handleAutoScroll(centroid.position.y)
                }
            }
            
            // Helper: Logic extracted to support calling from Timer
            function updateSelection() {
                var currentVisualX = centroid.position.x
                var currentVisualY = centroid.position.y
                
                // 1. Calculate Current Content Pos (Same logic as Start)
                var currentContentX = currentVisualX - rowListView.leftMargin
                var currentContentY = currentVisualY - rowListView.topMargin + rowListView.contentY
                
                // 2. Define Rect in CONTENT SPACE
                // (Min/Max between Start and Current)
                var x = Math.min(startContentX, currentContentX)
                var y = Math.min(startContentY, currentContentY)
                var w = Math.abs(currentContentX - startContentX)
                var h = Math.abs(currentContentY - startContentY)
                
                // 3. Update Visual RubberBand (Project back to Visual Space)
                // Visual X = Content X + leftMargin
                // Visual Y = Content Y - contentY + topMargin
                rubberBand.x = x + rowListView.leftMargin
                rubberBand.y = y - rowListView.contentY + rowListView.topMargin
                rubberBand.width = w
                rubberBand.height = h
                
                // 4. Query Backend (Pass Content Rect)
                var items = rowBuilder.getItemsInRect(x, y, w, h)
                
                // 5. Select
                var isCtrl = (marqueeHandler.centroid.modifiers & Qt.ControlModifier)
                selectionModel.selectRange(items, isCtrl)
            }
            
            // Helper: Detect Edges
            function handleAutoScroll(mouseY) {
                var threshold = 60 // Slightly larger active area
                var baseSpeed = 5  // Slower start for precision
                var maxBonus = 60  // Higher max speed (Total ~65px/frame)
                
                if (mouseY < threshold) {
                    // Top Edge -> Scroll Up (Negative)
                    var intensity = (threshold - mouseY) / threshold
                    // Cubic Acceleration: intensity^3 gives detailed control at low speeds, massive kick at high speeds
                    var speed = baseSpeed + maxBonus * Math.pow(intensity, 3)
                    
                    autoScrollTimer.scrollSpeed = -speed
                    if (!autoScrollTimer.running) autoScrollTimer.start()
                    
                } else if (mouseY > rowListView.height - threshold) {
                    // Bottom Edge -> Scroll Down (Positive)
                    var intensity = (mouseY - (rowListView.height - threshold)) / threshold
                    var speed = baseSpeed + maxBonus * Math.pow(intensity, 3)
                    
                    autoScrollTimer.scrollSpeed = speed
                    if (!autoScrollTimer.running) autoScrollTimer.start()
                    
                } else {
                    // Safe Zone
                    autoScrollTimer.stop()
                }
            }
        }
        
        Components.RubberBand {
            id: rubberBand
            visible: false 
        }
    }
}
