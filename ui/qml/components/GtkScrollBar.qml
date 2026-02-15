import QtQuick
import QtQuick.Controls

/**
 * GtkScrollBar - A thin, auto-hiding scrollbar that mirrors GNOME/GTK behavior.
 * 
 * Features:
 * - Expanding thumb (4.5px -> 9px) on hover.
 * - Auto-hides after 2 seconds of inactivity.
 * - Reappears on mouse movement over target, scrolling, or focus activity.
 */
ScrollBar {
    id: control

    // The Flickable (ListView/GridView) this scrollbar controls
    property Flickable flickable: parent
    
    active: hovered || pressed || activityTimer.running
    interactive: true
    hoverEnabled: true
    
    // Track: Transparent
    background: null

    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // Logic: Auto-hide timer
    Timer {
        id: activityTimer
        interval: 2000
        onTriggered: stop()
    }

    // Activity Trigger: Scrolling
    Connections {
        target: flickable
        function onContentYChanged() { activityTimer.restart() }
        function onContentXChanged() { activityTimer.restart() }
    }

    // Activity Trigger: Mouse Movement over the target area
    HoverHandler {
        target: flickable
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onPointChanged: activityTimer.restart()
    }

    // Activity Trigger: Focus/Key events (when attached to a focused item)
    Connections {
        target: flickable
        function onActiveFocusChanged() { if (flickable.activeFocus) activityTimer.restart() }
    }

    // VISUALS
    contentItem: Rectangle {
        implicitWidth: control.hovered || control.pressed ? 9 : 4.5 
        radius: width / 2
        
        // Color: Adaptive opacity based on state
        color: control.pressed ? activePalette.text : 
               control.hovered ? Qt.alpha(activePalette.text, 0.7) : 
               Qt.alpha(activePalette.text, 0.4)
        
        // Animations: Smooth GTK feel
        Behavior on implicitWidth { NumberAnimation { duration: 100 } }
        Behavior on color { ColorAnimation { duration: 150 } }
    }
}
