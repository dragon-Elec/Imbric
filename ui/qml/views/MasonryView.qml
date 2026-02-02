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
                            id: delegateWrapper
                            width: root.columnWidth
                            height: fileDelegate.height
                            
                            // Selection state (computed here, passed to delegate)
                            readonly property bool selected: selectionModel.selection.indexOf(model.path) !== -1

                            Components.FileDelegate {
                                id: fileDelegate
                                anchors.fill: parent
                                
                                // Model roles
                                path: model.path
                                name: model.name
                                isDir: model.isDir
                                isVisual: model.isVisual
                                iconName: model.iconName
                                modelWidth: model.modelWidth
                                modelHeight: model.modelHeight
                                index: model.index
                                
                                // View layout
                                columnWidth: root.columnWidth
                                
                                // State props
                                selected: delegateWrapper.selected
                                renamingPath: root.pathBeingRenamed
                                cutPaths: appBridge ? appBridge.cutPaths : []
                                
                                // Services
                                appBridge: appBridge
                                selectionModel: selectionModel
                                
                                // Handle rename events
                                onRenameCommitted: root.pathBeingRenamed = ""
                                onRenameCancelled: {
                                    root.pathBeingRenamed = ""
                                    rubberBandArea.forceActiveFocus()
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
            // hoverEnabled: true -- BLOCKS underlying items! Only needed if we tracked cursor without drag.
            
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
