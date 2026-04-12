import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import Qt.labs.animation

// Standalone, reusable breadcrumb/address bar component.
Rectangle {
    id: root

    // --- Public API ---
    property string currentPath: "" // Keep text up-to-date
    property var pathSegments: []
    property bool canGoBack: false // Used to enable/disable back button if needed elsewhere
    property color textColor: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark ? "white" : "black"
    property var palette: SystemPalette { colorGroup: SystemPalette.Active }
    
    signal pathRequested(string path)
    signal backRequested()

    function rejectPathError() {
        if (root.isEditing) {
            addressInput.triggerError()
        }
    }

    // --- Internal State & Styling ---
    readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    property bool isEditing: false
    onIsEditingChanged: console.log("[DEBUG] BreadcrumbAddressBar: isEditing =", isEditing)

    ListModel {
        id: internalModel
    }

    Timer {
        id: removalTimer
        interval: 150
        onTriggered: {
            for (let i = internalModel.count - 1; i >= 0; i--) {
                if (internalModel.get(i).is_removing) {
                    internalModel.remove(i, 1);
                }
            }
        }
    }

    onPathSegmentsChanged: {
        if (!pathSegments) return;
        
        let activeIndices = [];
        for (let i = 0; i < internalModel.count; i++) {
            if (!internalModel.get(i).is_removing) {
                activeIndices.push(i);
            }
        }
        
        let matchCount = 0;
        let minLen = Math.min(activeIndices.length, pathSegments.length);
        
        // Find exactly how many leading crumbs match our currently active ones
        for (let i = 0; i < minLen; i++) {
            let modelIdx = activeIndices[i];
            if (internalModel.get(modelIdx).target_path === pathSegments[i].target_path) {
                matchCount++;
            } else {
                break;
            }
        }
        
        // Prune off the mismatched/outdated right-hand tail with a smooth fade-out
        let wasCount = activeIndices.length;
        if (wasCount > matchCount) {
            // Flag the outgoing tail for animation
            for (let i = matchCount; i < wasCount; i++) {
                internalModel.setProperty(activeIndices[i], "is_removing", true);
            }
            // Execute the physical sweep 150ms later after they visually melt away
            removalTimer.restart();
        }
        
        // Append the brand new crumbs into the right-hand tail
        for (let i = matchCount; i < pathSegments.length; i++) {
            let obj = pathSegments[i];
            internalModel.append({
                "name": obj.name !== undefined ? obj.name : "",
                "icon": obj.icon !== undefined ? obj.icon : "",
                "is_active": obj.is_active !== undefined ? obj.is_active : false,
                "is_future": obj.is_future !== undefined ? obj.is_future : false,
                "is_first": obj.is_first !== undefined ? obj.is_first : false,
                "target_path": obj.target_path !== undefined ? obj.target_path : "",
                "is_removing": false
            });
        }
        
        // Pass active states and metadata updates downstream to the surviving crumbs silently
        for (let i = 0; i < matchCount; i++) {
            let modelIdx = activeIndices[i];
            let obj = pathSegments[i];
            internalModel.setProperty(modelIdx, "name", obj.name !== undefined ? obj.name : "");
            internalModel.setProperty(modelIdx, "icon", obj.icon !== undefined ? obj.icon : "");
            internalModel.setProperty(modelIdx, "is_active", obj.is_active !== undefined ? obj.is_active : false);
            internalModel.setProperty(modelIdx, "is_future", obj.is_future !== undefined ? obj.is_future : false);
            internalModel.setProperty(modelIdx, "is_first", obj.is_first !== undefined ? obj.is_first : false);
            internalModel.setProperty(modelIdx, "is_removing", false);
        }
    }

    // Height and sizing are now handled by the parent layout
    // Layout.fillWidth: true -> Now set on the instance in main.qml
    // Layout.alignment: Qt.AlignVCenter -> Now set on the instance in main.qml
    // Layout.preferredHeight: 32 -> Now set on the instance in main.qml
    
    // Recessed look fixing GTK/Zorin Theme Tinting
    // We explicitly hardcode pure #FFFFFF (or dark grey) for Edit Mode so it always looks paper-crisp like Nautilus
    color: isEditing ? (isSystemDark ? "#2A2A2A" : "#FFFFFF") : 
           (isSystemDark ? Qt.darker(palette.window, 1.1) : Qt.darker(palette.window, 1.025))
           
    // Softened the active border color significantly so it's not 'radioactive yellow'
    border.color: isEditing ? Qt.alpha(palette.highlight, 0.6) : 
                  (isSystemDark ? Qt.alpha(palette.windowText, 0.12) : Qt.alpha(palette.windowText, 0.1))
    border.width: isEditing ? 2 : 1
    radius: 8 // Softer radius to match modern GTK
    clip: true

    Behavior on color { ColorAnimation { duration: 150 } }
    Behavior on border.color { ColorAnimation { duration: 150 } }
    // Animate the thickness change so it feels like a soft 'pop' rather than a hard snap
    Behavior on border.width { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    
    // (Input focus logic moved to AddressInput component)

    // (Internal shortcut removed in favor of ActionManager/ShellManager global chain)

    // --- Child Components ---
    
    // 1. Breadcrumbs Mode (Visible when not editing)
    Item {
        id: breadcrumbContainer
        anchors.fill: parent
        // Container is now full height to allow 'Full Height' gloss/fades
        anchors.leftMargin: 1
        anchors.rightMargin: 1
        anchors.topMargin: 0
        anchors.bottomMargin: 0
        opacity: root.isEditing ? 0.0 : 1.0
        visible: opacity > 0
        enabled: !root.isEditing // Kill interaction instantly during fade
        clip: true

        Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutQuint } }

        Flickable {
            id: breadcrumbView
            anchors.fill: parent
            anchors.topMargin: 2 // Crumbs still need breathing room
            anchors.bottomMargin: 2
            anchors.leftMargin: 4 // Fixed padding — does NOT add scrollable area
            anchors.rightMargin: 4
            contentWidth: rowLayout.width
            contentHeight: height
            clip: false // Allow fades to draw over
            interactive: false // WheelHandler + BoundaryRule are the sole scroll controllers
            boundsBehavior: Flickable.StopAtBounds
            
            NumberAnimation {
                id: scrollAnim
                target: breadcrumbView
                property: "contentX"
                duration: 170
                easing.type: Easing.OutQuint
            }
        
            function ensureCrumbVisible(crumbItem) {
                Qt.callLater(() => {
                    // Prevent execution if items are actively being destroyed
                    if (!crumbItem || !breadcrumbView) return;
                    
                    let crumbX = crumbItem.x;
                    let crumbWidth = crumbItem.width;
                    
                    let pad = 40; // Generous breathing room so the crumb isn't touching the edge
                    let minX = 0;
                    let maxX = Math.max(0, breadcrumbView.contentWidth - breadcrumbView.width);
                    
                    let currentX = breadcrumbView.contentX;
                    let targetX = currentX;
                    
                    // Is the crumb clipped by the left side?
                    if (crumbX < currentX + pad) {
                        targetX = crumbX - pad;
                    } 
                    // Is the crumb clipped by the right side?
                    else if ((crumbX + crumbWidth) > (currentX + breadcrumbView.width - pad)) {
                        targetX = (crumbX + crumbWidth) - breadcrumbView.width + pad;
                    }
                    
                    // Hard clamp our calculated target bounds mathematically
                    targetX = Math.max(minX, Math.min(maxX, targetX));
                    
                    // Only start animation if we actually need to scroll
                    if (Math.abs(targetX - currentX) > 1) {
                        scrollAnim.to = targetX;
                        scrollAnim.restart();
                    }
                });
            }

            // --- Native Scrolling Logic ---
            // Uses WheelHandler to map vertical mouse wheel to horizontal contentX
            WheelHandler {
                id: wheelHandler
                target: breadcrumbView
                property: "contentX"
                orientation: Qt.Vertical // Vertical wheel -> Horizontal movement
                rotationScale: 0.5 // Adjust for smooth, high-precision feel
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                blocking: false
            }

            // --- Native Bound Enforcement (Hard Cap) ---
            BoundaryRule on contentX {
                id: xRule
                minimum: 0
                maximum: Math.max(0, breadcrumbView.contentWidth - breadcrumbView.width)
                minimumOvershoot: 0
                maximumOvershoot: 0
            }

            Row {
                id: rowLayout
                height: parent.height
                
                add: Transition {
                    NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: 150; easing.type: Easing.OutQuint }
                    NumberAnimation { property: "scale"; from: 0.9; to: 1.0; duration: 150; easing.type: Easing.OutQuint }
                }
                move: Transition {
                    NumberAnimation { properties: "x,y"; duration: 150; easing.type: Easing.OutQuint }
                }

                Repeater {
                    model: internalModel

                    delegate: Crumb {
                        id: crumbDelegate
                        
                        opacity: (model.is_removing !== undefined && model.is_removing) ? 0.0 : 1.0
                        scale: (model.is_removing !== undefined && model.is_removing) ? 0.9 : 1.0
                        
                        Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutQuint } }
                        Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutQuint } }
                        
                        text: model.name !== undefined ? model.name : ""
                        iconSource: model.icon !== undefined ? model.icon : ""
                        isActive: model.is_active !== undefined ? model.is_active : false
                        isFuture: model.is_future !== undefined ? model.is_future : false
                        isFirst: model.is_first !== undefined ? model.is_first : false
                        // In Nemo style, all items have separators except the very last one in the entire list
                        showSeparator: index !== internalModel.count - 1
                        textColor: root.textColor
                        palette: root.palette
                        
                        onClicked: {
                            if (model.is_active) {
                                root.isEditing = true
                            } else {
                                root.pathRequested(model.target_path)
                            }
                        }
                        onRequestVisible: breadcrumbView.ensureCrumbVisible(crumbDelegate)
                    }
                }
            }
        }

        // --- Background TapHandler (Trigger Edit Mode) ---
        // This covers the entire area that is not specifically consumed by crumbs
        TapHandler {
            acceptedButtons: Qt.LeftButton
            onTapped: root.isEditing = true
            enabled: !root.isEditing
        }

        // --- Premium Fade Effect ---
        // --- Premium Fade Effect ---
        Rectangle {
            id: leftFade
            width: 32 // +20% width for a longer, smoother tail
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            radius: root.radius // Matches the root radius for full-height alignment
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.alpha(root.palette.highlight, 0.30) }
                GradientStop { position: 0.6; color: Qt.alpha(root.palette.highlight, 0.08) }
                GradientStop { position: 1.0; color: "transparent" }
            }
            // Visible only when scrolled significantly away from the start
            visible: breadcrumbView.contentX > 1 
        }

        Rectangle {
            id: rightFade
            width: 32 // +20% width for a longer, smoother tail
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            radius: root.radius // Matches the root radius for full-height alignment
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.4; color: Qt.alpha(root.palette.highlight, 0.08) }
                GradientStop { position: 1.0; color: Qt.alpha(root.palette.highlight, 0.30) }
            }
            // Visible only when there is significant scrollable area left
            visible: breadcrumbView.contentX < breadcrumbView.contentWidth - breadcrumbView.width - 1
        }
        
    }

    // 2. Text Input Mode (Visible when editing)
    AddressInput {
        id: addressInput
        anchors.fill: parent
        text: root.currentPath
        textColor: root.textColor
        palette: root.palette
        isActive: root.isEditing

        onAccepted: (newText) => {
            root.pathRequested(newText)
            // We intentionally do NOT set root.isEditing = false here.
            // If the backend accepts the path, main.qml's onPathChanged listener closes it.
            // If the backend rejects the path, it stays open to shake.
        }
        onCanceled: {
            root.isEditing = false
            root.forceActiveFocus() // Drop focus from input
        }
    }

}
