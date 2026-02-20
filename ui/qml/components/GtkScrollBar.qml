import QtQuick
import QtQuick.Controls

/**
 * GtkScrollBar - A thin, auto-hiding scrollbar that mirrors GNOME/GTK behavior.
 * 
 * Features:
 * - Expanding thumb (4.5px -> 9px) on hover.
 * - Auto-hides after 2 seconds of inactivity.
 * - Optional "pillar" track (showTrack: true).
 * - Self-contained geometry logic + optional external flickable binding.
 */
ScrollBar {
    id: control

    // --- CONFIGURATION ---
    // Optional: Flickable binding for manual usage (triggers activity)
    property Flickable flickable: null
    // Optional: Show a subtle background track when active
    property bool showTrack: false
    
    // --- PHYSICS CONFIGURATION ---
    // Toggle internal physics engine
    property bool physicsEnabled: false
    // Enable "Turbo" acceleration curve (faster ramp-up)
    property bool turboMode: true
    // Current acceleration multiplier
    property real acceleration: 1.0

    // Internal State for Physics
    property real lastWheelTime: 0
    property int lastDeltaSign: 0
    
    // Physics Timer for "SnapBack" (overshoot recovery)
    Timer {
        id: snapBackTimer
        interval: 150 
        onTriggered: {
            if (!control.flickable) return
            // Dynamic Bounds: Respect margins (paddings)
            let minY = -control.flickable.topMargin
            let maxY = Math.max(minY, control.flickable.contentHeight - control.flickable.height + control.flickable.bottomMargin)
            
            if (control.flickable.contentY < minY) {
                control.flickable.contentY = minY
            } else if (control.flickable.contentY > maxY) {
                control.flickable.contentY = maxY
            }
        }
    }

    // --- PHYSICS ENGINE ---
    
    // Public API: Call this from parent's WheelHandler
    function handleWheel(event) {
        if (!control.physicsEnabled || !control.flickable) return

        // Dynamic Bounds
        let minY = -control.flickable.topMargin
        let maxY = Math.max(minY, control.flickable.contentHeight - control.flickable.height + control.flickable.bottomMargin)
        
        if (maxY < 20) return

        // 1. Acceleration Logic
        let now = new Date().getTime()
        let dt = now - control.lastWheelTime
        control.lastWheelTime = now
        
        let currentSign = (event.angleDelta.y > 0) ? 1 : -1
        
        if (dt < 100 && currentSign === control.lastDeltaSign && event.angleDelta.y !== 0) {
             let ramp = control.turboMode ? 1.0 : 0.5   
             let limit = control.turboMode ? 10.0 : 6.0 
             control.acceleration = Math.min(control.acceleration + ramp, limit)
        } else {
             control.acceleration = 1.0
        }
        control.lastDeltaSign = currentSign

        // 2. Calculate Delta
        let delta = 0
        if (event.angleDelta.y !== 0) {
             delta = -(event.angleDelta.y / 1.2)
             delta *= control.acceleration
        } else if (event.pixelDelta.y !== 0) {
            delta = -event.pixelDelta.y
        } 
        
        if (delta === 0) return

        // 3. Resistance (Rubber Banding)
        if (control.flickable.contentY < minY || control.flickable.contentY > maxY) {
            delta *= 0.3
        }

        // 4. Apply with Clamped Overshoot Limits
        let newY = control.flickable.contentY + delta
        if (newY < minY - 300) newY = minY - 300
        if (newY > maxY + 300) newY = maxY + 300
        
        control.flickable.contentY = newY
        
        snapBackTimer.restart()
        activityTimer.restart()
    }

    // fallback: Internal handler (only works if hovering scrollbar directly)
    // We keep this for cases where user HOVERS the scrollbar itself
    WheelHandler {
        target: null // Logic handled via function call
        enabled: control.physicsEnabled
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: (event) => control.handleWheel(event)
    }

    // --- LOGIC ---
    // Active when hovered, pressed, or recently used (timer)
    active: hovered || pressed || activityTimer.running
    
    // Only render when content is scrollable (size < 1.0) and valid
    visible: control.size < 1.0 && control.size > 0
    
    interactive: true
    hoverEnabled: true

    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // Auto-hide Timer
    Timer {
        id: activityTimer
        interval: 2000
        onTriggered: stop()
    }

    // --- ACTIVITY TRIGGERS ---
    // 1. Internal Geometry Changes (Works universally)
    onPositionChanged: activityTimer.restart()
    onSizeChanged: activityTimer.restart()
    
    // 2. Mouse Interaction
    onHoveredChanged: if (hovered) activityTimer.restart()
    
    // 3. External Flickable Signals (if bound)
    Connections {
        target: flickable
        function onContentYChanged() { activityTimer.restart() }
        function onContentXChanged() { activityTimer.restart() }
        function onMovementStarted() { activityTimer.restart() }
        ignoreUnknownSignals: true
    }
    
    // 4. Parent View Interactivity (if parent is Flickable/ListView)
    // This handles the "unhide on scroll/hover" feature requested
    Connections {
        target: control.parent && control.parent.flickableItem ? control.parent.flickableItem : (control.parent instanceof Flickable ? control.parent : null)
        function onMovementStarted() { activityTimer.restart() }
        ignoreUnknownSignals: true
    }

    // --- VISUALS ---
    
    // Background Track (Pillar) - Optional
    background: Rectangle {
        visible: control.showTrack && control.active
        // Ensure track fills the scrollbar area
        anchors.fill: parent
        // Slightly more visible color for testing/usage
        color: Qt.alpha(activePalette.windowText, 0.1)
        opacity: control.active ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    // Thumb
    contentItem: Rectangle {
        implicitWidth: control.hovered || control.pressed ? 9 : 4.5 
        radius: width / 2
        
        // Color: Adaptive opacity based on state
        color: control.pressed ? activePalette.text : 
               control.hovered ? Qt.alpha(activePalette.text, 0.7) : 
               Qt.alpha(activePalette.text, 0.4)
        
        // Fade in/out
        opacity: control.active ? 1.0 : 0.0
        
        // Animations: Smooth GTK feel
        Behavior on implicitWidth { NumberAnimation { duration: 100 } }
        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
}
