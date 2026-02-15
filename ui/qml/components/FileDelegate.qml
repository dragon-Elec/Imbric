import QtQuick
import QtQuick.Controls
import components as Components

/**
 * FileDelegate — Reusable file/folder item for JustifiedView
 * 
 * Accepts explicit dimensions from parent (JustifiedView/RowDelegate).
 * Does NOT calculate its own height — that's the parent's job.
 */
Item {
    id: delegateRoot

    Component.onCompleted: {
        // console.log("[FileDelegate] Created for:", path, "Width:", width, "Height:", imageHeight)
    }


    // =========================================================================
    // 1. MODEL DATA CONTRACT (Bound from parent - nested component pattern)
    // =========================================================================
    required property string path
    required property string name
    required property bool isDir
    required property bool isVisual
    required property string iconName
    property int modelWidth: 0   // Renamed from 'width', not required to prevent undefined errors
    property int modelHeight: 0  // Renamed from 'height', not required to prevent undefined errors
    required property int index

    // =========================================================================
    // 2. VIEW LAYOUT CONTRACT (Must be passed explicitly from parent)
    // =========================================================================
    required property int imageHeight  // Fixed height from JustifiedView/RowDelegate
    property real columnWidth: 200     // Width calculated from aspect ratio
    property int thumbnailMaxWidth: 0   // 0 = no cap (icons/vectors can scale)
    property int thumbnailMaxHeight: 0  // Actual thumbnail cache dimensions

    // =========================================================================
    // 3. STATE PROPS (Passed from parent for styling)
    // =========================================================================
    property string renamingPath: ""
    property var cutPaths: []
    property bool selected: false

    // =========================================================================
    // 4. SERVICES (Passed from parent - per-tab context)
    // =========================================================================
    property var bridge: null
    property var selModel: null
    property var rowBuilder: null

    // =========================================================================
    // 5. SIGNALS (For parent to handle)
    // =========================================================================
    signal renameCommitted(string newName)
    signal renameCancelled()
    // Interaction Signals (Bubbling up to Parent)
    signal clicked(int button, int modifiers)
    signal doubleClicked()

    // =========================================================================
    // 6. COMPUTED PROPERTIES
    // =========================================================================
    width: columnWidth
    
    readonly property bool isBeingRenamed: renamingPath === path

    // Fixed height from parent (no dynamic calculation)
    readonly property int footerHeight: 36
    height: imageHeight + footerHeight
    
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
            if (delegateRoot.selected) return Qt.alpha(activePalette.highlight, 0.4)
            if (delegateRoot.isDir && itemDropArea.containsDrag) return Qt.alpha(activePalette.highlight, 0.6)
            if (delegateHoverHandler.hovered) return Qt.rgba(activePalette.text.r, activePalette.text.g, activePalette.text.b, 0.1)
            return "transparent"
        }
        
        // Dim items that are in "cut" state (pending move)
        opacity: (cutPaths && cutPaths.indexOf(path) >= 0) ? 0.5 : 1.0
        
        // Photo Thumbnail (Async, Cached Bitmap)
        // Photo Thumbnail (Async, Cached Bitmap)
        // [FIX] Letterboxing Container
        // This Item defines the "Active Area" of the cell.
        Item {
            id: imgContainer
            visible: isVisual
            
            // Container fills the cell space minus padding
            width: parent.width - 8
            height: delegateRoot.imageHeight - 8
            
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.topMargin: 4
            
            Image {
                id: img
                
                // [FIX] Dynamic Resolution Cap
                readonly property int maxCap: Math.max(delegateRoot.thumbnailMaxWidth, delegateRoot.thumbnailMaxHeight)
                
                width: maxCap > 0 ? Math.min(parent.width, maxCap) : parent.width
                height: maxCap > 0 ? Math.min(parent.height, maxCap) : parent.height
                
                anchors.centerIn: parent
                
                source: isVisual ? (bridge ? bridge.getThumbnailPath(path) : "") : ""
                
                // Use Fit to ensure we see the whole image within our box
                fillMode: Image.PreserveAspectFit
                
                asynchronous: true
                cache: true
                mipmap: false // [FIX] Disabled for sharper downscaling (matches Nemo)
                
                // Request at fixed display size for efficiency
                // sourceSize: Qt.size(width, height)

                // SHIMMER EFFECT: Visual feedback during loading
                Rectangle {
                    anchors.fill: parent
                    color: activePalette.midlight
                    visible: img.status === Image.Loading
                    
                    Gradient {
                        id: shimmerGradient
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.3) }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                    
                    Rectangle {
                        id: shimmerBar
                        width: parent.width
                        height: parent.height
                        gradient: shimmerGradient
                        opacity: 0.5
                        
                        NumberAnimation on x {
                            from: -shimmerBar.width
                            to: shimmerBar.width
                            duration: 1000
                            loops: Animation.Infinite
                            running: img.status === Image.Loading
                        }
                    }
                }
            }
        }
        
        // Theme Icon (Vector, Crisp at Any Size)
        Image {
            id: themeIcon
            visible: !isVisual
            width: parent.width - 8
            height: delegateRoot.imageHeight - 8
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
            // LAYOUT FIX: Anchor to the bottom of the CARD (parent), not the image.
            // This guarantees text never overlaps image, even if aspect ratio drifts.
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
                color: activePalette.text
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
                    if (newName !== name && bridge) {
                        bridge.renameFile(path, newName)
                    }
                    delegateRoot.renameCommitted(newName)
                }
                
                onCancel: {
                    delegateRoot.renameCancelled()
                }
            }
        }
        
        // HoverHandler removed (using MouseArea.hoverEnabled)
    }
    
    // =========================================================================
    // 9. INTERACTION HANDLERS
    // =========================================================================
    
    // 1. MOUSE AREA (Handles Clicks & Context Menu locally)
    // 1. INPUT HANDLERS (Replaces MouseArea for non-blocking interaction)
    
    // 1a. Hover Handler (Visual Feedback)
    HoverHandler {
        id: delegateHoverHandler
        // No blocking, purely for hover state detection
    }

    // 1b. Left Click Handler (Single & Double Click)
    TapHandler {
        id: leftClickHandler
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.ReleaseWithinBounds // EXCLUSIVE GRAB: Helper stops propagation to parent handlers upon release
        acceptedModifiers: Qt.KeyboardModifierMask // Allow Ctrl, Shift, etc. to be captured by this handler

        onTapped: (eventPoint, button) => {
            console.log("[FileDelegate] TapHandler Tapped:", path)
            console.log("  - Button:", button)
            console.log("  - Modifiers:", eventPoint.modifiers)
            console.log("  - Qt.LeftButton:", Qt.LeftButton)
            
            // Modifiers access logic
            // Try handler's own point property (often more reliable than signal argument in some Qt versions)
            let mod = eventPoint.modifiers
            if (mod === undefined) {
                 mod = leftClickHandler.point.modifiers
                 console.log("  - Fallback to leftClickHandler.point.modifiers:", mod)
            }
            if (mod === undefined) {
                 mod = Qt.application.keyboardModifiers
                 console.log("  - Fallback to Qt.application.keyboardModifiers:", mod)
            }
             
            delegateRoot.clicked(Qt.LeftButton, mod !== undefined ? mod : 0)
        }

        onDoubleTapped: (eventPoint, button) => {
             console.log("[Delegate] Double Click:", path)
             delegateRoot.doubleClicked()
        }
    }

    // 1c. Right Click Handler (Context Menu)
    TapHandler {
        id: rightClickHandler
        acceptedButtons: Qt.RightButton
        gesturePolicy: TapHandler.WithinBounds // More forgiving than DragThreshold
        acceptedModifiers: Qt.KeyboardModifierMask

        onTapped: (eventPoint, button) => {
            console.log("[Delegate] Right Click:", path)
            delegateRoot.clicked(Qt.RightButton, eventPoint.modifiers)
        }
    }

    // 2. Drop Area for Folders (Allows dragging files INTO a folder)
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
                if (bridge) {
                    bridge.handleDrop(urls, path)
                }
            }
        }
    }
    
    // 4. DragHandler for Drag-and-Drop (initiating drag FROM this item)
    DragHandler {
        id: delegateDragHandler
        target: null // Don't move the visual
        
        // Assert Dominance: Win against parent marquee
        grabPermissions: PointerHandler.CanTakeOverFromAnything

        onActiveChanged: {
            if (active) {
                console.log("[Delegate] Drag Started on:", path)
                // Ensure item is selected before starting drag
                if (!delegateRoot.selected && selModel) {
                    selModel.select(path)
                }
                if (bridge && selModel) {
                    bridge.startDrag(selModel.selection)
                }
            }
        }
    }
}
