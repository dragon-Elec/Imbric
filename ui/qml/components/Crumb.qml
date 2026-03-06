import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl

/**
 * Crumb.qml
 * Individual segment of the breadcrumb bar.
 */
Item {
    id: root
    
    // --- Public API ---
    property string text: ""
    property string iconSource: ""
    property bool isActive: false
    property bool isFuture: false
    property bool isFirst: false
    property bool showSeparator: true
    property color textColor: "black"
    property var palette
    
    // --- Feedback States ---
    property real loadProgress: 0.0 // 0.0 to 1.0 for spring-loading
    property bool isWorking: false  // Indeterminate 'loading' pulse for slow paths (SMB/Network)
    property real pulseOpacity: 1.0 // Private property for animation pulse

    signal clicked()
    signal requestVisible()

    onIsActiveChanged: {
        if (isActive) Qt.callLater(() => root.requestVisible())
    }
    
    Component.onCompleted: {
        if (isActive) Qt.callLater(() => root.requestVisible())
    }
    
    onXChanged: {
        if (isActive) Qt.callLater(() => root.requestVisible())
    }

    implicitWidth: contentRow.implicitWidth + (showSeparator ? separator.width : 0)
    // Safe height calculation; Repeater directly parents to the layout Row
    height: parent ? parent.height : 28

    Row {
        id: contentRow
        height: parent.height
        spacing: 0

        Rectangle {
            id: btn
            height: parent.height - 4
            anchors.verticalCenter: parent.verticalCenter
            width: contentItem.width + 11
            radius: 4
            clip: true // Required to mask the shimmer overlay inside the rounded corners
            
            // Add subtle spring logic for premium click feel
            scale: tapHandler.pressed ? 0.96 : 1.0
            Behavior on scale { 
                NumberAnimation { duration: 120; easing.type: Easing.OutQuint } 
            }

            // The exact frame 0.0 of releasing a click starts the isExiting timer.
            // Treating isExiting identically to isActive + hovered guarantees the color never 
            // dips into the weak inactive state while waiting for the model to update.
            color: tapHandler.pressed ? Qt.alpha(root.palette.highlight, 0.40) : 
                   dropArea.containsDrag ? Qt.alpha(root.palette.highlight, 0.50) : 
                   (root.isActive || isExiting) ? ((hoverHandler.hovered || isExiting) ? Qt.alpha(root.palette.highlight, 0.30) : Qt.alpha(root.palette.highlight, 0.20)) :
                   (hoverHandler.hovered ? Qt.alpha(root.palette.highlight, 0.12) : "transparent")
            
            // Highlight border when working (Network activity)
            border.color: root.isWorking ? root.palette.highlight : "transparent"
            border.width: 1
            
            Behavior on color { 
                ColorAnimation { duration: 150; easing.type: Easing.OutQuint } 
            }

            // --- Premium Shimmer / Gloss Overlay for 'Working' State ---
            Rectangle {
                id: shimmer
                y: 0
                width: 45 // Short and small
                height: parent.height
                visible: root.loadProgress > 0 || shimmerAnim.running
                
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    // Dense opacity at the center, adaptive to theme colors (acting as pure light/shadow)
                    GradientStop { position: 0.5; color: Qt.alpha(root.textColor, 0.40) }
                    GradientStop { position: 1.0; color: "transparent" }
                }

                SequentialAnimation on x {
                    id: shimmerAnim
                    loops: Animation.Infinite
                    running: root.loadProgress > 0
                    
                    NumberAnimation {
                        from: -shimmer.width
                        to: btn.width + shimmer.width
                        duration: 900
                        easing.type: Easing.InOutQuad
                    }
                    PauseAnimation { duration: 800 } // Slight pause between sweeps for a natural reflection feel
                }
            }

            // --- Premium Progress Feedback (Spring Loading) ---
            Rectangle {
                id: progressBar
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                height: 2
                width: parent.width * root.loadProgress
                color: root.palette.highlight
                visible: root.loadProgress > 0
                opacity: 0.8
                radius: 1
            }
            
            Row {
                id: contentItem
                anchors.centerIn: parent
                spacing: 6
                
                // System Icon (Native rendering via C++ engine)
                IconImage {
                    id: iconItem
                    name: root.iconSource
                    visible: root.iconSource !== ""
                    sourceSize: Qt.size(16, 16)
                    // Hybrid coloring strategy: tint symbolic, pass-through full color
                    color: root.iconSource.endsWith("-symbolic") ? root.textColor : "transparent"
                    opacity: hoverHandler.hovered || root.isActive ? 1.0 : 0.7
                }

                Text {
                    id: textItem
                    text: root.text
                    color: root.textColor
                    opacity: root.isWorking ? root.pulseOpacity : (hoverHandler.hovered || root.isActive ? 1.0 : (root.isFuture ? 0.4 : 0.7))
                    font.bold: root.isActive
                    font.pixelSize: 13
                    font.family: Qt.application.font.family
                    renderType: Text.NativeRendering
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    // Standard eliding logic carried over
                    width: Math.min(implicitWidth, 200) 
                    
                    // Behavior on opacity removed to prevent conflict with pulse animation
                }
            }

            DropArea {
                id: dropArea
                anchors.fill: parent
                // In the future this will accept URIs/Files
                keys: ["text/uri-list", "application/x-qabstractitemmodeldatalist"]
                
                onEntered: if (!root.isActive) springTimer.restart()
                onExited: springTimer.stop()
                onDropped: springTimer.stop()
            }
            
            Timer {
                id: springTimer
                interval: 800
                repeat: false
                onTriggered: {
                    if (dropArea.containsDrag && !root.isActive) {
                        successPop.start()
                        root.clicked()
                    }
                }
            }

            // --- Control Logic for Animations ---
            NumberAnimation {
                id: progressFill
                target: root
                property: "loadProgress"
                from: 0; to: 1.0
                duration: springTimer.interval
                easing.type: Easing.Linear
            }

            SequentialAnimation {
                id: successPop
                ScaleAnimator { target: btn; from: 1.0; to: 1.15; duration: 100 }
                ScaleAnimator { target: btn; from: 1.15; to: 1.0; duration: 200; easing.type: Easing.OutQuint }
            }

            NumberAnimation {
                id: workingPulse
                target: root 
                property: "pulseOpacity"
                from: 0.3; to: 1.0
                duration: 1000
                loops: Animation.Infinite
                running: root.isWorking
                easing.type: Easing.InOutSine
            }


            Connections {
                target: dropArea
                function onContainsDragChanged() {
                    if (dropArea.containsDrag && !root.isActive) {
                        progressFill.start()
                        springTimer.restart()
                    } else {
                        if (!hoverHandler.hovered) { // Only stop if we aren't also simulating via hover below
                           progressFill.stop()
                           springTimer.stop()
                           root.loadProgress = 0
                        }
                    }
                }
            }

            // Prevent hover color recalculations from tearing during the exit animation
            property bool isExiting: clickDelayTimer.running

            // --- Interaction Logic (Left / Right / Middle) ---
            TapHandler {
                id: tapHandler
                acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                gesturePolicy: TapHandler.ReleaseWithinBounds // Exclusively grab tap to stop CSD Window Menu
                
                onTapped: (point, button) => {
                    if (button === Qt.LeftButton) {
                        // Let the physical 120ms shrink/unshrink animation finish, THEN navigate.
                        clickDelayTimer.start();
                    } 
                    else if (button === Qt.MiddleButton) {
                        // Testing mock logic requested by the designer to preview network loading
                        root.isWorking = !root.isWorking;
                    }
                    else if (button === Qt.RightButton) {
                        // Swallow right-click to prevent the CSD Window Menu from appearing underneath
                        // TODO: Map to an internal breadcrumb folder context menu in the future
                        if (!root.isActive) {
                            progressFill.start();
                            springTimer.restart();
                        }
                    } 
                }
            }
            
            HoverHandler {
                id: hoverHandler
                // Lock the hover state if we are already transitioning out
                enabled: !btn.isExiting
                cursorShape: Qt.PointingHandCursor
                blocking: false
            }
            
            Timer {
                id: clickDelayTimer
                interval: 130 // 10ms padding over the 120ms scale animation
                repeat: false
                onTriggered: root.clicked()
            }
        }

        // Separator logic moved inside the component for better containment
        Label {
            id: separator
            text: "/"
            visible: root.showSeparator
            color: root.textColor
            opacity: 0.3
            height: parent.height
            verticalAlignment: Text.AlignVCenter
            leftPadding: 1.5
            rightPadding: -4
            font.pixelSize: 18
            font.family: Qt.application.font.family
            renderType: Text.NativeRendering
        }
    }
}
