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
    
    // Services (Ensure appBridge is available globally or injected)
    // In some contexts, appBridge might be context property, but let's be explicit if needed.
    // Define property to resolve global context
    property var bridge: appBridge
    
    // EXPOSED PROPERTY: For Python Key Shortcuts (Copy/Cut/Trash)
    property alias currentSelection: selectionModel.selection
    
    // EXPOSED FUNCTION: For Python to set selection (e.g., after paste)
    function selectPaths(paths) {
        selectionModel.selection = paths
    }

    // EXPOSED FUNCTION: For Python select-all shortcut
    function selectAll() {
        selectionModel.selectAll(columnSplitter.getAllItems())
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

        // ROOT CONTAINER
        Rectangle {
            anchors.fill: parent
            color: activePalette.base
            focus: true // Root container takes focus by default if nothing else has it

            // Layer 1: Content
            ScrollView {
            id: scrollView
            anchors.fill: parent
            clip: true
            
            // CONTAINER: Wraps content so ScrollView sees a single child
            Item {
                id: contentContainer
                // Width: At least window width, but grows if content is wider
                implicitWidth: Math.max(scrollView.availableWidth, columnsRow.width + 20)
                // Height: At least window height (for marquee in empty space), but grows with content
                implicitHeight: Math.max(scrollView.availableHeight, columnsRow.height + 20)

                // 1. MARQUEE & BACKGROUND HANDLER
                // Handles Marquee Selection & Background Clicks
                MouseArea {
                    id: marqueeArea
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    hoverEnabled: false 
                    preventStealing: true // Prevents ScrollView from panning when we are dragging the marquee

                    // ZOOM SUPPORT (Ctrl + Wheel)
                    onWheel: (wheel) => {
                        if (wheel.modifiers & Qt.ControlModifier) {
                            let zoomDelta = wheel.angleDelta.y > 0 ? 1 : -1
                            if (root.bridge) root.bridge.zoom(zoomDelta)
                            wheel.accepted = true
                        } else {
                            wheel.accepted = false // Let ScrollView handle normal scroll
                        }
                    }

                    property point startPoint
                    property bool isDragging: false

                    onPressed: (mouse) => {
                        // RIGHT CLICK: Background Context Menu
                        if (mouse.button === Qt.RightButton) {
                            console.log("[Background] Right Click -> Menu")
                            if (root.bridge) root.bridge.showBackgroundContextMenu()
                            return
                        }

                        // LEFT CLICK: Start Marquee Check
                        startPoint = Qt.point(mouse.x, mouse.y)
                        isDragging = false
                        
                        // "Eat" the event to prevent ScrollView from Panning (Touch style)
                        mouse.accepted = true
                        rubberBandArea.forceActiveFocus()
                        root.pathBeingRenamed = ""
                    }
                    
                    onPositionChanged: (mouse) => {
                        // Logic: Only start drag after threshold
                        if (!isDragging && (Math.abs(mouse.x - startPoint.x) > 5 || Math.abs(mouse.y - startPoint.y) > 5)) {
                            isDragging = true
                            rubberBand.visible = true
                            rubberBand.update(startPoint.x, startPoint.y, startPoint.x, startPoint.y)
                        }
                        
                        if (isDragging) {
                            rubberBand.update(startPoint.x, startPoint.y, mouse.x, mouse.y)
                            
                            // SELECTION LOGIC
                            // Map Marquee Rect to ColumnsRow (for SelectionHelper)
                            var rect = rubberBand.getRect()
                            // contentContainer is the parent of columnsRow, so coords are already roughly correct,
                            // but let's be precise if columnsRow has margins.
                            var mappedPt = columnsRow.mapFromItem(contentContainer, rect.x, rect.y)
                            
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
                        if (mouse.button === Qt.LeftButton) {
                            if (isDragging) {
                                rubberBand.visible = false
                                isDragging = false
                            } else {
                                // Simple Click on Background -> Clear Selection
                                selectionModel.clear()
                            }
                        }
                    }
                    
                    // 3. RUBBER BAND VISUAL
                    Components.RubberBand {
                        id: rubberBand
                        visible: false
                        z: 100 
                    }
                }

                // 2. THE CONTENT (Files)
                Row {
                    id: columnsRow
                    // LEFT ALIGNMENT: No anchor to horizontalCenter. 
                    // Use margins to give a little breathing room.
                    x: 10 
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
                            
                            delegate: Components.FileDelegate {
                                id: fileDelegate
                                
                                // 1. DATA BINDINGS
                                modelWidth: model.modelWidth || 0
                                modelHeight: model.modelHeight || 0

                                // 2. VIEW LAYOUT
                                columnWidth: root.columnWidth
                                
                                // 3. STATE PROPS
                                selected: root.currentSelection.indexOf(path) !== -1
                                renamingPath: root.pathBeingRenamed
                                cutPaths: appBridge ? appBridge.cutPaths : []
                                
                                // Services
                                bridge: appBridge
                                selModel: selectionModel
                                
                                // Handle rename events
                                onRenameCommitted: root.pathBeingRenamed = ""
                                onRenameCancelled: {
                                    root.pathBeingRenamed = ""
                                    rubberBandArea.forceActiveFocus()
                                }

                                // 4. INTERACTIONS
                                onClicked: (button, modifiers) => {
                                    console.log("[MasonryView] Delegate Clicked:", path)
                                    if (button === Qt.RightButton) {
                                        if (!selectionModel.isSelected(path)) selectionModel.select(path)
                                        appBridge.showContextMenu(selectionModel.selection)
                                    } else {
                                        var ctrl = (modifiers & Qt.ControlModifier)
                                        var shift = (modifiers & Qt.ShiftModifier)
                                        selectionModel.handleClick(path, ctrl, shift, columnSplitter.getAllItems())
                                    }
                                }
                                onDoubleClicked: {
                                    console.log("[MasonryView] Delegate DoubleClicked:", path)
                                    appBridge.openPath(path)
                                }
                            }
                        }
                    }
                }
            }
        }
        
        // Layer 2: Background Interaction (Pointer Handlers)
        // [MOVED TO contentContainer MOUSEAREA]

        // 3. RUBBER BAND VISUAL
        // [MOVED TO contentContainer MOUSEAREA]
        
        // Dummy Item for Focus stealing (fallback)
        Item { id: rubberBandArea; focus: true }

        // Layer 3: Drop Area (Handles incoming files)
        DropArea {
            anchors.fill: parent
            z: -1 // Behind items
            
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
