import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import components as Components  // Shared library

Item {
    id: root
    
    // Python properties
    property var columnModels: columnSplitter.getModels()
    property int columnCount: columnModels ? columnModels.length : 0
    property real columnWidth: appBridge ? appBridge.targetCellWidth : 250
    
    // EXPOSED PROPERTY: For Python Key Shortcuts (Copy/Cut/Trash)
    property alias currentSelection: selectionModel.selection
    
    // EXPOSED FUNCTION: For Python to set selection (e.g., after paste)
    function selectPaths(paths) {
        selectionModel.selection = paths
    }
    
    // STATE: Inverse of SelectionModel, tracks which ONE file is being renamed
    property string pathBeingRenamed: ""
    
    Connections {
        target: appBridge
        function onRenameRequested(path) {
            root.pathBeingRenamed = path
        }
    }

    // --- LIBRARY COMPONENTS ---
    Components.SelectionModel {
        id: selectionModel
    }

    // --- SYSTEM PALETTE ---
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // --- ROOT CONTAINER ---
    Rectangle {
        anchors.fill: parent
        color: activePalette.base
        focus: true // Root container takes focus by default if nothing else has it

        // Global Key Handler (F2)
        Keys.onPressed: (event) => {
            if (event.isAutoRepeat) return
            
            if (event.key === Qt.Key_F2) {
                var sel = selectionModel.selection
                if (sel.length === 1) {
                    if (root.pathBeingRenamed === sel[0]) {
                        root.pathBeingRenamed = ""
                        rubberBandArea.forceActiveFocus()
                    } else {
                        root.pathBeingRenamed = sel[0]
                    }
                    event.accepted = true
                }
            }
        }

        // Layer 1: Content
        ScrollView {
            id: scrollView
            anchors.fill: parent
            clip: true
            
            Row {
                id: columnsRow
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 10
                
                Repeater {
                    id: columnRepeater
                    model: root.columnModels
                    
                    delegate: ListView {
                        id: columnListView
                        width: root.columnWidth
                        interactive: false
                        height: contentHeight
                        model: modelData
                        
                        delegate: Item {
                            id: delegateItem
                            width: root.columnWidth
                            
                            readonly property real imgHeight: {
                                if (model.isDir) return width * 0.8
                                
                                // 1. Fast Path: Use model dimensions if known (stable layout)
                                if (model.width > 0 && model.height > 0) 
                                    return (model.height / model.width) * width
                                
                                // 2. Deferred Path: Use loaded thumbnail dimensions
                                if (img.status === Image.Ready && img.implicitWidth > 0)
                                    return (img.implicitHeight / img.implicitWidth) * width
                                    
                                // 3. Loading State: Square placeholder
                                return width
                            }
                            readonly property int footerHeight: 36
                            height: imgHeight + footerHeight
                            
                            // Fix reactivity: Direct binding is safer than function call which might hide dependency
                            readonly property bool selected: selectionModel.selection.indexOf(model.path) !== -1

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 4
                                radius: 4
                                
                                // Color Logic:
                                // 1. Selected -> Highlight
                                // 2. Drag Over Folder -> Highlight (Visual Feedback)
                                // 3. Hover -> Light tint
                                color: {
                                    if (delegateItem.selected) return activePalette.highlight
                                    if (model.isDir && itemDropArea.containsDrag) return activePalette.highlight
                                    if (hoverHandler.hovered) return Qt.rgba(activePalette.text.r, activePalette.text.g, activePalette.text.b, 0.1)
                                    return "transparent"
                                }
                                
                                // Dim items that are in "cut" state (pending move)
                                // Safety check: appBridge might be null during shutdown
                                opacity: (appBridge && appBridge.cutPaths && appBridge.cutPaths.indexOf(model.path) >= 0) ? 0.5 : 1.0
                                
                                // Drop Area for Folders (Allows dragging files INTO a folder)
                                DropArea {
                                    id: itemDropArea
                                    anchors.fill: parent
                                    enabled: model.isDir // Only folders accept drops
                                    
                                    onEntered: (drag) => {
                                        drag.accept(Qt.CopyAction)
                                    }
                                    
                                    onDropped: (drop) => {
                                        if (drop.hasUrls) {
                                            drop.accept()
                                            var urls = []
                                            for (var i = 0; i < drop.urls.length; i++) {
                                                urls.push(drop.urls[i].toString())
                                            }
                                            // Handle drop INTO this folder
                                            appBridge.handleDrop(urls, model.path)
                                        }
                                    }
                                }
                                
                                // Photo Thumbnail (Async, Cached Bitmap)
                                Image {
                                    id: img
                                    visible: model.isVisual
                                    width: parent.width - 8
                                    height: delegateItem.imgHeight - 8
                                    anchors.top: parent.top
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.topMargin: 4
                                    
                                    source: model.isVisual ? "image://thumbnail/" + model.path : ""
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: true
                                }
                                
                                // Theme Icon (Vector, Crisp at Any Size)
                                Image {
                                    id: themeIcon
                                    visible: !model.isVisual
                                    width: parent.width - 8
                                    height: delegateItem.imgHeight - 8
                                    anchors.top: parent.top
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.topMargin: 4
                                    
                                    // Qt's theme engine handles SVG/PNG selection
                                    source: !model.isVisual ? "image://theme/" + model.iconName : ""
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: false  // Theme icons are fast (no I/O)
                                    cache: false         // Re-render at current size on zoom
                                    
                                    // Request icon at current display size for crispness
                                    sourceSize: Qt.size(width, height)
                                }
                                
                                Item {
                                    anchors.bottom: parent.bottom
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottomMargin: 4
                                    width: parent.width - 8
                                    height: 20

                                    Text {
                                        anchors.fill: parent
                                        text: model.name
                                        visible: root.pathBeingRenamed !== model.path
                                        color: (delegateItem.selected || (model.isDir && itemDropArea.containsDrag)) ? activePalette.highlightedText : activePalette.text
                                        font.pixelSize: 12
                                        elide: Text.ElideMiddle
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    Components.RenameField {
                                        anchors.fill: parent
                                        visible: root.pathBeingRenamed === model.path
                                        active: visible
                                        originalName: model.name
                                        
                                        onCommit: (newName) => {
                                            if (newName !== model.name) {
                                                appBridge.renameFile(model.path, newName)
                                            }
                                            root.pathBeingRenamed = ""
                                        }
                                        
                                        onCancel: {
                                            root.pathBeingRenamed = ""
                                            rubberBandArea.forceActiveFocus()
                                        }
                                    }
                                }
                                
                                HoverHandler { id: hoverHandler }
                                
                                // TapHandler removed: Logic moved to global MouseArea for reliable modifier support
                                // DragHandler remains for Drag-and-Drop (handled separately)
                                DragHandler {
                                    id: delegateDragHandler
                                    target: null // Don't move the visual
                                    
                                    onActiveChanged: {
                                        if (active) {
                                            // Ensure item is selected before starting drag
                                            if (!delegateItem.selected) {
                                                selectionModel.select(model.path)
                                            }
                                            appBridge.startDrag(selectionModel.selection)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        // Layer 2: Background Interaction (ON TOP but passes item events through)
        // Handles: Rubberband selection, background clicks, zoom
        MouseArea {
            id: rubberBandArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            hoverEnabled: true
            
            property point startPoint
            property bool isDragging: false
            property bool wasMarqueeSelecting: false // Survives release-click sequence
            property bool isOnItem: false // Track if press was on an item

            // Zoom Support (Ctrl+Scroll)
            onWheel: (wheel) => {
                if (wheel.modifiers & Qt.ControlModifier) {
                    var delta = wheel.angleDelta.y > 0 ? -1 : 1
                    appBridge.zoom(delta)
                    wheel.accepted = true
                } else {
                    wheel.accepted = false
                }
            }

            onPressed: (mouse) => {
                wasMarqueeSelecting = false
                
                // --- 1. Accurate Hit-Test using QML ---
                // We ask the specific ListView column: "Is there an item under this pixel?"
                // This handles padding, margins, and exact rendering perfectly.
                isOnItem = false
                
                // Map global mouse to the Row (which handles the scrolling offset)
                var rowPt = columnsRow.mapFromItem(root, mouse.x, mouse.y)
                
                // Find which column we are over
                // (Assuming equal width + spacing)
                var totalColWidth = root.columnWidth + columnsRow.spacing
                var colIndex = Math.floor(rowPt.x / totalColWidth)
                
                if (colIndex >= 0 && colIndex < columnRepeater.count) {
                    var targetListView = columnRepeater.itemAt(colIndex)
                    if (targetListView) {
                        // Map Row point to ListView (should be just local X adjustment)
                        var lvPt = targetListView.mapFromItem(columnsRow, rowPt.x, rowPt.y)
                        
                        // Check indexAt in the ListView
                        // Note: MasonryView uses expanded ListView (non-interactive), 
                        // so contentY is effectively 0 relative to the Item itself,
                        // but let's be safe and use standard lookup.
                        var idx = targetListView.indexAt(lvPt.x, lvPt.y)
                        
                        if (idx !== -1) {
                            // WE HIT AN ITEM!
                            isOnItem = true
                            
                            // Retrieve Data from Python Model
                            var itemData = targetListView.model.get(idx)
                            if (itemData && itemData.path) {
                                if (mouse.button === Qt.RightButton) {
                                    // Right Click Logic
                                    if (!selectionModel.isSelected(itemData.path)) {
                                        selectionModel.select(itemData.path)
                                    }
                                    appBridge.showContextMenu(selectionModel.selection)
                                } else {
                                    // Left Click Logic
                                    // Using mouse.modifiers directly from the MouseArea (Reliable!)
                                    var ctrl = (mouse.modifiers & Qt.ControlModifier)
                                    var shift = (mouse.modifiers & Qt.ShiftModifier)
                                    selectionModel.handleClick(itemData.path, ctrl, shift, columnSplitter.getAllItems())
                                }
                            }
                            
                            mouse.accepted = true // Consume event
                            return
                        }
                    }
                }
                
                // --- 2. Background Interaction ---
                // If we got here, we clicked the background (gaps or empty space)
                
                // Don't start marquee if renaming
                if (root.pathBeingRenamed !== "") {
                    // If renaming, background click should confirm (or cancel?)
                    // Currently handled by TextField focus loss or other logic, 
                    // but let's consume it to be safe.
                     // Actually, we want to let the focus change happen?
                     // Let's consume it to prevent clearing selection immediately 
                     // if that is desired, OR let it clear.
                     // Standard behavior: Click outside -> Commit & Deselect?
                     // For now, let's just NOT start marquee.
                    mouse.accepted = false
                    return
                }
                
                // Start marquee on empty space
                startPoint = Qt.point(mouse.x, mouse.y)
                isDragging = false
            }

            onPositionChanged: (mouse) => {
                if (isOnItem) return // Item is handling this
                if (!(mouse.buttons & Qt.LeftButton)) return
                
                // Start marquee after small movement
                if (!isDragging && (Math.abs(mouse.x - startPoint.x) > 5 || Math.abs(mouse.y - startPoint.y) > 5)) {
                    isDragging = true
                    rubberBand.show()
                }

                if (isDragging) {
                    rubberBand.update(startPoint.x, startPoint.y, mouse.x, mouse.y)
                    
                    var rect = rubberBand.getRect()
                    var mappedPt = columnsRow.mapFromItem(root, rect.x, rect.y)
                    
                    var hits = selectionHelper.getMasonrySelection(
                        columnSplitter, 
                        root.columnCount, 
                        root.columnWidth, 
                        10,
                        mappedPt.x, 
                        mappedPt.y, 
                        rect.width, 
                        rect.height
                    )
                    selectionModel.selectRange(hits, (mouse.modifiers & Qt.ControlModifier))
                }
            }

            onReleased: (mouse) => {
                rubberBand.hide()
                if (isDragging) {
                    wasMarqueeSelecting = true // Mark that we just did a marquee
                }
                isDragging = false
            }

            onClicked: (mouse) => {
                // Skip if we just finished marquee selection or if we're on an item
                if (wasMarqueeSelecting || isOnItem) return
                
                // Click on empty space (not a drag, not on item)
                if (mouse.button === Qt.RightButton) {
                    selectionModel.clear()
                    appBridge.showBackgroundContextMenu()
                } else {
                    selectionModel.clear()
                }
            }
            
            onDoubleClicked: (mouse) => {
                // Replicate Hit-Test logic for Open action
                var rowPt = columnsRow.mapFromItem(root, mouse.x, mouse.y)
                var totalColWidth = root.columnWidth + columnsRow.spacing
                var colIndex = Math.floor(rowPt.x / totalColWidth)
                
                if (colIndex >= 0 && colIndex < columnRepeater.count) {
                    var targetListView = columnRepeater.itemAt(colIndex)
                    if (targetListView) {
                        var lvPt = targetListView.mapFromItem(columnsRow, rowPt.x, rowPt.y)
                        var idx = targetListView.indexAt(lvPt.x, lvPt.y)
                        
                        if (idx !== -1) {
                            var itemData = targetListView.model.get(idx)
                            if (itemData && itemData.path && mouse.button === Qt.LeftButton) {
                                appBridge.openPath(itemData.path)
                            }
                        }
                    }
                }
            }
            
            // RubberBand visual
            Components.RubberBand {
                id: rubberBand
            }
        }
        // Layer 3: Drop Area (Handles incoming files)
        DropArea {
            anchors.fill: parent
            z: -1 // Behind items (items will get drops first if we add DropArea to them later)
            
            onEntered: (drag) => {
                drag.accept(Qt.CopyAction)
            }
            
            onDropped: (drop) => {
                if (drop.hasUrls) {
                    drop.accept()
                    // Convert URLs to array of strings
                    var urls = []
                    for (var i = 0; i < drop.urls.length; i++) {
                        urls.push(drop.urls[i].toString())
                    }
                    appBridge.handleDrop(urls, "") // Empty string = current dir
                }
            }
        }
    }
    
    Connections {
        target: columnSplitter
        function onColumnsChanged() { root.columnModels = columnSplitter.getModels() }
    }
}
