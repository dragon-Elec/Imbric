import QtQuick
import QtQuick.Controls

TextField {
    id: root
    
    // --- API ---
    property string originalName: ""
    property bool active: false
    
    signal commit(string newName)
    signal cancel()

    // --- STATE ---
    text: originalName
    font.pixelSize: 12
    
    // --- STYLING ---
    background: Rectangle {
        color: activePalette.base
        border.color: activePalette.highlight
        border.width: 1
        radius: 2
    }
    
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }
    
    color: activePalette.text
    selectedTextColor: activePalette.highlightedText
    selectionColor: activePalette.highlight
    
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
    
    focus: active
    selectByMouse: true
    
    // --- BEHAVIOR ---
    
    function initSession() {
        forceActiveFocus()
        // Select filename without extension
        var name = text
        var lastDot = name.lastIndexOf(".")
        if (lastDot > 0) {
            select(0, lastDot)
        } else {
            selectAll()
        }
    }
    
    onActiveChanged: if (active) initSession()
    Component.onCompleted: if (active) initSession()
    
    // 1. Commit on Enter
    onAccepted: {
        root.commit(text)
        focus = false // Release focus
    }
    
    // 2. Commit on Focus Loss (Clicking away)
    onActiveFocusChanged: {
        if (!activeFocus && active) {
            // We lost focus while active -> Commit
            root.commit(text)
        }
    }
    
    // 3. Cancel on Escape
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape) {
            root.cancel()
            event.accepted = true
        }
    }
}
