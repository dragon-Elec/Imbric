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

        // 2. DropArea — External file drops
        DropArea {
            anchors.fill: parent
            onEntered: (drag) => drag.accept(Qt.CopyAction)
            onDropped: (drop) => {
                if (drop.hasUrls) {
                    drop.accept()
                    var urls = []
                    for (var i = 0; i < drop.urls.length; i++) 
                        urls.push(drop.urls[i].toString())
                    root.bridge.handleDrop(urls, "")
                }
            }
        }

        // 3. Background Actions (Deselect / Context Menu)
        // Placed as siblings to ListView. Since ListView is interactive: false, 
        // clicks on empty areas should pass through or be handled here.
        TapHandler {
            acceptedButtons: Qt.LeftButton
            acceptedModifiers: Qt.KeyboardModifierMask // Don't clear selection if user is Ctrl-clicking empty space
            onTapped: {
                selectionModel.clear()
                root.forceActiveFocus()
                root.pathBeingRenamed = ""
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

        // 4. Main List View (Direct, no ScrollView wrapper)
        ListView {
            id: rowListView
            anchors.fill: parent
            clip: true
            
            // Interaction:
            // - False: Disables native Flickable drag (fixes click conflict).
            // - True: We would lose empty-area clicks.
            interactive: false 

            // ScrollBar: Attached directly. 
            // "active: true" keeps it visible/fading correctly.
            // "interactive: true" ensures we can drag it even if ListView is interactive: false.
            // ScrollBar: Specialized GTK component
            ScrollBar.vertical: Components.GtkScrollBar {
                flickable: rowListView
            }

            // Physics State
            property real lastWheelTime: 0
            property real acceleration: 1.0
            property int lastDeltaSign: 0
            property bool turboMode: true // Defaulted to true for testing

            // SnapBack Timer: Returns to bounds after overshooting
            Timer {
                id: snapBackTimer
                interval: 150 
                onTriggered: {
                    let maxY = Math.max(0, rowListView.contentHeight - rowListView.height)
                    if (rowListView.contentY < 0) {
                        rowListView.contentY = 0
                    } else if (rowListView.contentY > maxY) {
                        rowListView.contentY = maxY
                    }
                }
            }

            // Wheel Handling: Custom logic to inject smooth scrolls
            // We do this manually because interactive: false kills native wheeling too.
            WheelHandler {
                target: rowListView
                onWheel: (event) => {
                    let maxY = Math.max(0, rowListView.contentHeight - rowListView.height)

                    // Optimization: Micro-overflow check (STRICT MODE)
                    // RISK: If contentY gets stuck out of bounds (e.g. negative) due to resize/scrollbar drag,
                    // this strict check WILL prevent the wheel from recovering it.
                    // The view will be frozen until a resize or scrollbar interaction resets it.
                    if (maxY < 20) {
                        return
                    }
                    
                    // 1. Acceleration Logic
                    let now = new Date().getTime()
                    let dt = now - rowListView.lastWheelTime
                    rowListView.lastWheelTime = now
                    
                    // If same direction and fast (<100ms), ramp up acceleration
                    // (Only relevant for Mouse Wheel steps, but we calculate it generally)
                    let currentSign = (event.angleDelta.y > 0) ? 1 : -1
                    if (dt < 100 && currentSign === rowListView.lastDeltaSign && event.angleDelta.y !== 0) {
                         let ramp = rowListView.turboMode ? 1.0 : 0.5   
                         let limit = rowListView.turboMode ? 10.0 : 6.0 
                         
                         rowListView.acceleration = Math.min(rowListView.acceleration + ramp, limit)
                    } else {
                         rowListView.acceleration = 1.0
                    }
                    rowListView.lastDeltaSign = currentSign

                    // 2. Base Delta & Acceleration Handling
                    let delta = 0
                    let isTrackpad = false
                    
                    if (event.angleDelta.y !== 0) {
                         // Mouse Wheel: Apply Acceleration
                         delta = -(event.angleDelta.y / 1.2)
                         delta *= rowListView.acceleration
                    } else if (event.pixelDelta.y !== 0) {
                        // Trackpad: Direct 1:1 Mapping (No Turbo/Acceleration)
                        delta = -event.pixelDelta.y
                        isTrackpad = true
                    } 
                    
                    if (delta === 0) return

                    // 3. Resistance (Bounce)
                    // If we are ALREADY out of bounds, apply heavy friction
                    if (rowListView.contentY < 0 || rowListView.contentY > maxY) {
                        delta *= 0.3
                    }

                    // 4. Propose New Position
                    let newY = rowListView.contentY + delta

                    // 5. Relaxed Clamping (Allow Overshoot up to 300px)
                    if (newY < -300) newY = -300
                    if (newY > maxY + 300) newY = maxY + 300
                    
                    // 6. Apply
                    rowListView.contentY = newY
                    
                    // Restart SnapBack
                    snapBackTimer.restart()
                }
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
                x: 10
            }

            onWidthChanged: {
                if (rowBuilder) rowBuilder.setAvailableWidth(width)
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
                var maxY = Math.max(0, rowListView.contentHeight - rowListView.height)
                newY = Math.max(0, Math.min(newY, maxY))
                
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
                    startContentX = start.x - 10        // Correct for padding
                    startContentY = start.y + rowListView.contentY
                    
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
                
                // 1. Calculate Current Content Pos
                var currentContentX = currentVisualX - 10
                var currentContentY = currentVisualY + rowListView.contentY
                
                // 2. Define Rect in CONTENT SPACE
                // (Min/Max between Start and Current)
                var x = Math.min(startContentX, currentContentX)
                var y = Math.min(startContentY, currentContentY)
                var w = Math.abs(currentContentX - startContentX)
                var h = Math.abs(currentContentY - startContentY)
                
                // 3. Update Visual RubberBand (Project back to Visual Space)
                // VisualY = ContentY - rowListView.contentY
                // VisualX = ContentX + 10
                rubberBand.x = x + 10
                rubberBand.y = y - rowListView.contentY
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
