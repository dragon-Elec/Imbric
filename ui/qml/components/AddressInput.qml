import QtQuick
import QtQuick.Controls

Item {
    id: root

    property alias text: pathInput.text
    property color textColor: "black"
    property var palette
    property bool isActive: false

    signal accepted(string text)
    signal canceled()

    opacity: isActive ? 1.0 : 0.0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

    function triggerError() {
        errorAnim.restart()
    }

    transform: Translate { id: errorTranslate; x: 0 }

    SequentialAnimation {
        id: errorAnim
        NumberAnimation { target: errorTranslate; property: "x"; from: 0; to: 4; duration: 40 }
        NumberAnimation { target: errorTranslate; property: "x"; from: 4; to: -4; duration: 40 }
        NumberAnimation { target: errorTranslate; property: "x"; from: -4; to: 4; duration: 40 }
        NumberAnimation { target: errorTranslate; property: "x"; from: 4; to: -4; duration: 40 }
        NumberAnimation { target: errorTranslate; property: "x"; from: -4; to: 0; duration: 40 }
    }

    onIsActiveChanged: {
        if (isActive) {
            pathInput.forceActiveFocus()
            pathInput.selectAll()
        }
    }

    // --- Focus Containment ---
    // The FocusScope ensures that focus is 'trapped' within this component
    // while it is active, preventing flutters.
    TextField {
        id: pathInput
        text: root.text
        
        // 1. Fill the entire bar to prevent 'dead zone' focus loss
        anchors.fill: parent
        anchors.rightMargin: cancelEditBtn.width + 4
        
        // 1. Native Typography (Soft & System-Native)
        renderType: Text.NativeRendering
        font.pixelSize: 14 // Dropped slightly so it's not bulky
        font.family: Qt.application.font.family
        font.weight: Font.Normal // Ensure it never defaults to Bold
        
        // 2. Soft Highlight Math

        // By forcing the selected text to stay standard textColor, we fix the 'unreadable white text' 
        // bug and mimic GTK's translucent selection boxes over dark text.
        color: errorAnim.running ? "#ff483bff" : root.textColor 
        selectionColor: Qt.alpha(root.palette.highlight, 0.35)
        selectedTextColor: root.textColor

        verticalAlignment: Text.AlignVCenter
        leftPadding: 12 // Increased for breathing room mimicking a real address bar
        rightPadding: 8
        
        // 3. Transparent Background
        // We let the parent BreadcrumbAddressBar container handle the border and background
        // to avoid the 'double border' regression.
        background: Item {}
        
        TapHandler {
            acceptedButtons: Qt.RightButton
            onTapped: contextMenu.popup()
        }
        
        Menu {
            id: contextMenu
            MenuItem { text: "Cut"; onTriggered: pathInput.cut(); enabled: pathInput.selectedText.length > 0 }
            MenuItem { text: "Copy"; onTriggered: pathInput.copy(); enabled: pathInput.selectedText.length > 0 }
            MenuItem { text: "Paste"; onTriggered: pathInput.paste(); enabled: pathInput.canPaste }
            MenuSeparator {}
            MenuItem { text: "Select All"; onTriggered: pathInput.selectAll() }
        }

        onActiveFocusChanged: console.log("[DEBUG] AddressInput: TextField activeFocus =", activeFocus)

        // Auto-dismiss logic removed in favor of the Overlay strategy
        
        onAccepted: root.accepted(text)
        Keys.onEscapePressed: root.canceled()
    }

    // Exit Edit Mode Button
    ToolButton {
        id: cancelEditBtn
        text: "✕"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: 2
        width: height
        focusPolicy: Qt.NoFocus // Crucial
        
        contentItem: Text { 
            text: parent.text; 
            color: root.textColor; 
            opacity: 0.7
            horizontalAlignment: Text.AlignHCenter; 
            verticalAlignment: Text.AlignVCenter; 
            font.pixelSize: 14
            font.family: Qt.application.font.family
        }
        
        onClicked: root.canceled()
    }
}
