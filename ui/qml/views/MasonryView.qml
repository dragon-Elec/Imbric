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
                                if (model.width > 0 && model.height > 0) return (model.height / model.width) * width
                                return width
                            }
                            readonly property int footerHeight: 36
                            height: imgHeight + footerHeight
                            
                            readonly property bool selected: selectionModel.isSelected(model.path)

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
                                
                                Image {
                                    width: parent.width - 8
                                    height: delegateItem.imgHeight - 8
                                    anchors.top: parent.top
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.topMargin: 4
                                    
                                    source: "image://thumbnail/" + model.path
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: true
                                }
                                
                                Text {
                                    anchors.bottom: parent.bottom
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottomMargin: 4
                                    width: parent.width - 8
                                    
                                    text: model.name
                                    color: (delegateItem.selected || (model.isDir && itemDropArea.containsDrag)) ? activePalette.highlightedText : activePalette.text
                                    font.pixelSize: 12
                                    elide: Text.ElideMiddle
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                
                                HoverHandler { id: hoverHandler }
                                
                                // Item Click & Context Menu -> Handled by Global MouseArea now
                            }
                        }
                    }
                }
            }
        }
        
        // Layer 2: RubberBand Interaction Overlay
        // HANDLES EVERYTHING: Clicks, drags, double-clicks.
        // Solves z-order issues by being the only top-level input handler.
        MouseArea {
            id: rubberBandArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            hoverEnabled: true
            // z: 0 (Default is on top of siblings defined before it)
            
            property point startPoint
            property string startPath: "" // If pressed on an item, this holds its path
            property bool isDragging: false
            property bool wasDragging: false 

            // Zoom Support (Ctrl+Scroll)
            onWheel: (wheel) => {
                if (wheel.modifiers & Qt.ControlModifier) {
                    // Scroll up = zoom in (larger icons), scroll down = zoom out (smaller icons)
                    var delta = wheel.angleDelta.y > 0 ? -1 : 1
                    appBridge.zoom(delta)
                    wheel.accepted = true
                } else {
                    wheel.accepted = false
                }
            }

            onPressed: (mouse) => {
                // Don't block scrollbar interaction (right 20px)
                if (mouse.x > scrollView.width - 20) {
                    mouse.accepted = false
                    return
                }
                
                startPoint = Qt.point(mouse.x, mouse.y)
                isDragging = false
                wasDragging = false
                mouse.accepted = true 
                startPath = ""
                
                // Identify if we pressed on an item
                var mappedPt = columnsRow.mapFromItem(root, mouse.x, mouse.y)
                var hits = selectionHelper.getMasonrySelection(
                    columnSplitter, 
                    root.columnCount, 
                    root.columnWidth, 
                    10,
                    mappedPt.x, 
                    mappedPt.y, 
                    1, 1 
                )
                
                if (hits.length > 0) {
                    startPath = hits[0]
                    // Do NOT select immediately on press if it's potentially a drag start
                    // We handle selection in onClicked or on drag start
                }
            }

            onPositionChanged: (mouse) => {
                if (!(mouse.buttons & Qt.LeftButton)) return
                
                if (!isDragging && (Math.abs(mouse.x - startPoint.x) > 10 || Math.abs(mouse.y - startPoint.y) > 10)) {
                    isDragging = true
                    
                    // DECISION: Drag Items OR RubberBand?
                    if (startPath !== "") {
                        // START SYSTEM DRAG
                        // Ensure item is selected before dragging
                        if (!selectionModel.isSelected(startPath)) {
                            selectionModel.select(startPath)
                        }
                        
                        // Start blocking system drag
                        appBridge.startDrag(selectionModel.selection)
                        
                        // Drag finished (because startDrag blocks)
                        isDragging = false 
                        wasDragging = true // suppress click
                    } else {
                        // START RUBBERBAND
                        rubberBand.show()
                    }
                }

                if (isDragging) {
                    // Only update rubberband if we are in rubberband mode (startPath is empty)
                    if (startPath === "") {
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
            }

            onReleased: (mouse) => {
                if (isDragging) {
                    rubberBand.hide()
                    wasDragging = true // Mark that we just finished dragging
                    isDragging = false
                }
            }

            onClicked: (mouse) => {
                if (isDragging || wasDragging) return
                
                // Get item at click position
                // We use a 1x1 rect to query the specific point
                var mappedPt = columnsRow.mapFromItem(root, mouse.x, mouse.y)
                var hits = selectionHelper.getMasonrySelection(
                    columnSplitter, 
                    root.columnCount, 
                    root.columnWidth, 
                    10,
                    mappedPt.x, 
                    mappedPt.y, 
                    1, 1 
                )
                
                var clickedPath = hits.length > 0 ? hits[0] : null
                
                if (mouse.button === Qt.RightButton) {
                    if (clickedPath) {
                        if (!selectionModel.isSelected(clickedPath)) {
                            selectionModel.select(clickedPath)
                        }
                        appBridge.showContextMenu(selectionModel.selection)
                    } else {
                         // Right click on empty space -> show background menu (Paste, New Folder)
                         selectionModel.clear()
                         appBridge.showBackgroundContextMenu()
                    }
                } else {
                     if (clickedPath) {
                         selectionModel.toggle(clickedPath, (mouse.modifiers & Qt.ControlModifier))
                     } else {
                         selectionModel.clear()
                     }
                }
            }
            
            onDoubleClicked: (mouse) => {
                // Double click to open
                if (mouse.button === Qt.LeftButton) {
                     var mappedPt = columnsRow.mapFromItem(root, mouse.x, mouse.y)
                     var hits = selectionHelper.getMasonrySelection(
                        columnSplitter, 
                        root.columnCount, 
                        root.columnWidth, 
                        10,
                        mappedPt.x, 
                        mappedPt.y, 
                        1, 1 
                    )
                    
                    if (hits.length > 0) {
                        appBridge.openPath(hits[0])
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
