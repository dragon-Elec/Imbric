import QtQuick
import QtQuick.Controls
import components as Components

/**
 * FileDelegate — Reusable file/folder item for MasonryView
 * 
 * Phase 1: ✅ Visuals (Image, Icon, Label)
 * Phase 2: ✅ Interaction handlers (DragHandler, DropArea)
 * Phase 3: ✅ RenameField integrated
 */
Item {
    id: delegateRoot

    // =========================================================================
    // 1. MODEL DATA CONTRACT (Bound from parent - nested component pattern)
    // =========================================================================
    required property string path
    required property string name
    required property bool isDir
    required property bool isVisual
    required property string iconName
    required property int modelWidth   // Renamed from 'width' to avoid FINAL conflict
    required property int modelHeight  // Renamed from 'height' to avoid FINAL conflict
    required property int index

    // =========================================================================
    // 2. VIEW LAYOUT CONTRACT (Must be passed explicitly from parent)
    // =========================================================================
    property real columnWidth: 200

    // =========================================================================
    // 3. STATE PROPS (Passed from parent for styling)
    // =========================================================================
    property string renamingPath: ""
    property var cutPaths: []
    property bool selected: false

    // =========================================================================
    // 4. SERVICES (Passed from parent - per-tab context)
    // =========================================================================
    property var appBridge: null
    property var selectionModel: null

    // =========================================================================
    // 5. SIGNALS (For parent to handle)
    // =========================================================================
    signal renameCommitted(string newName)
    signal renameCancelled()

    // =========================================================================
    // 6. COMPUTED PROPERTIES
    // =========================================================================
    width: columnWidth
    
    readonly property bool isBeingRenamed: renamingPath === path

    readonly property real imgHeight: {
        if (isDir) return width * 0.8
        
        // 1. Fast Path: Use model dimensions if known (stable layout)
        if (modelWidth > 0 && modelHeight > 0) 
            return (modelHeight / modelWidth) * width
        
        // 2. Deferred Path: Use loaded thumbnail dimensions
        if (img.status === Image.Ready && img.implicitWidth > 0)
            return (img.implicitHeight / img.implicitWidth) * width
            
        // 3. Loading State: Square placeholder
        return width
    }

    readonly property int footerHeight: 36
    height: imgHeight + footerHeight
    
    // Expose containsDrag for parent to use in selection logic if needed
    readonly property bool containsDrag: itemDropArea.containsDrag

    // =========================================================================
    // 7. SYSTEM PALETTE
    // =========================================================================
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // =========================================================================
    // 8. VISUAL IMPLEMENTATION
    // =========================================================================
    Rectangle {
        id: cardBackground
        anchors.fill: parent
        anchors.margins: 4
        radius: 4
        
        // Color Logic:
        // 1. Selected -> Highlight
        // 2. Drag Over Folder -> Highlight (Visual Feedback)
        // 3. Hover -> Light tint
        color: {
            if (delegateRoot.selected) return activePalette.highlight
            if (delegateRoot.isDir && itemDropArea.containsDrag) return activePalette.highlight
            if (hoverHandler.hovered) return Qt.rgba(activePalette.text.r, activePalette.text.g, activePalette.text.b, 0.1)
            return "transparent"
        }
        
        // Dim items that are in "cut" state (pending move)
        opacity: (cutPaths && cutPaths.indexOf(path) >= 0) ? 0.5 : 1.0
        
        // Photo Thumbnail (Async, Cached Bitmap)
        Image {
            id: img
            visible: isVisual
            width: parent.width - 8
            height: delegateRoot.imgHeight - 8
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 4
            
            source: isVisual ? "image://thumbnail/" + path : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: true
        }
        
        // Theme Icon (Vector, Crisp at Any Size)
        Image {
            id: themeIcon
            visible: !isVisual
            width: parent.width - 8
            height: delegateRoot.imgHeight - 8
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 4
            
            // Qt's theme engine handles SVG/PNG selection
            source: !isVisual ? "image://theme/" + iconName : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: false  // Theme icons are fast (no I/O)
            cache: false         // Re-render at current size on zoom
            
            // Request icon at current display size for crispness
            sourceSize: Qt.size(width, height)
        }
        
        // Footer with file name or RenameField
        Item {
            id: footerArea
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: 4
            width: parent.width - 8
            height: 20

            // Static text label (shown when NOT renaming)
            Text {
                anchors.fill: parent
                text: name
                visible: !delegateRoot.isBeingRenamed
                color: (delegateRoot.selected || (delegateRoot.isDir && itemDropArea.containsDrag)) 
                       ? activePalette.highlightedText 
                       : activePalette.text
                font.pixelSize: 12
                elide: Text.ElideMiddle
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            // Inline rename field (shown when renaming this item)
            Components.RenameField {
                anchors.fill: parent
                visible: delegateRoot.isBeingRenamed
                active: visible
                originalName: name
                
                onCommit: (newName) => {
                    if (newName !== name && appBridge) {
                        appBridge.renameFile(path, newName)
                    }
                    delegateRoot.renameCommitted(newName)
                }
                
                onCancel: {
                    delegateRoot.renameCancelled()
                }
            }
        }
        
        HoverHandler { id: hoverHandler }
    }
    
    // =========================================================================
    // 9. INTERACTION HANDLERS
    // =========================================================================
    
    // Drop Area for Folders (Allows dragging files INTO a folder)
    DropArea {
        id: itemDropArea
        anchors.fill: parent
        enabled: isDir // Only folders accept drops
        
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
                if (appBridge) {
                    appBridge.handleDrop(urls, path)
                }
            }
        }
    }
    
    // DragHandler for Drag-and-Drop (initiating drag FROM this item)
    DragHandler {
        id: delegateDragHandler
        target: null // Don't move the visual
        
        onActiveChanged: {
            if (active) {
                // Ensure item is selected before starting drag
                if (!delegateRoot.selected && selectionModel) {
                    selectionModel.select(path)
                }
                if (appBridge && selectionModel) {
                    appBridge.startDrag(selectionModel.selection)
                }
            }
        }
    }
}
