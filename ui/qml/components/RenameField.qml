import QtQuick
import QtQuick.Controls

TextArea {
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
    // Style to match native look
    background: Rectangle {
        color: activePalette.base
        border.color: activePalette.highlight
        border.width: 1
        radius: 2
    }
    
    // Note: SystemPalette must be available in parent context or we instantiate one
    // Ideally components should be self-contained, so let's check activePalette access.
    // Standard QtQuick SystemPalette usage:
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    color: activePalette.text
    selectedTextColor: activePalette.highlightedText
    selectionColor: activePalette.highlight
    
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
    
    focus: active
    selectByMouse: true
    
    // --- BEHAVIOR ---
    
    onActiveChanged: {
        if (active) {
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
    }
    
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
            root.commit(root.text)
            event.accepted = true
        } else if (event.key === Qt.Key_Escape) {
            root.cancel()
            event.accepted = true
        }
    }
}
