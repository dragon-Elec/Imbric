import QtQuick
import QtQuick.Controls

Text {
    id: iconRoot
    
    // --- Public API ---
    property string name: ""      // MD3 Ligature (e.g. "delete")
    property bool filled: false  // Toggle filled state
    property real weight: 400    // 100 to 700
    property real grade: 0       // -25 to 200
    property real size: 24       // Optical size match
    
    // --- Layout ---
    font.family: "Material Symbols Rounded"
    font.pixelSize: size
    text: name
    
    // Performance hint for text as icon
    renderType: Text.QtRendering
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    
    // --- "Elite" Variable Axis Control (Qt 6.10+) ---
    // Mapping our properties to the font's internal variable axes
    font.features: {
        "FILL": filled ? 1 : 0,
        "wght": weight,
        "GRAD": grade,
        "opsz": size
    }
    
    // --- Transitions ---
    Behavior on font.features {
        NumberAnimation { duration: 150; easing.type: Easing.OutQuint }
    }
    
    Behavior on color {
        ColorAnimation { duration: 150 }
    }
}
