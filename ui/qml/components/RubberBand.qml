import QtQuick

/**
 * RubberBand.qml
 * 
 * A reusable selection rectangle component, matching Qt's QRubberBand behavior.
 * 
 * Usage:
 *   RubberBand {
 *       id: rubberBand
 *       // Call update(x, y, w, h) from a MouseArea to set position/size
 *   }
 * 
 * Styling:
 *   - Uses SystemPalette.highlight for native theming.
 *   - Override 'fillColor' and 'borderColor' properties if needed.
 */
Rectangle {
    id: root
    
    // --- Theming ---
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }
    
    // Configurable colors (default to system theme)
    property color fillColor: Qt.rgba(activePalette.highlight.r, activePalette.highlight.g, activePalette.highlight.b, 0.3)
    property color borderColor: activePalette.highlight
    
    // --- Appearance ---
    visible: false
    color: fillColor
    border.color: borderColor
    border.width: 1
    
    // --- API ---
    
    /**
     * Updates the rubberband geometry.
     * Call this from your MouseArea's onPositionChanged handler.
     *
     * @param startX - X of the initial press
     * @param startY - Y of the initial press
     * @param currentX - Current mouse X
     * @param currentY - Current mouse Y
     */
    function update(startX, startY, currentX, currentY) {
        root.x = Math.min(startX, currentX)
        root.y = Math.min(startY, currentY)
        root.width = Math.abs(currentX - startX)
        root.height = Math.abs(currentY - startY)
    }
    
    /**
     * Shows the rubberband.
     */
    function show() {
        root.visible = true
    }
    
    /**
     * Hides the rubberband.
     */
    function hide() {
        root.visible = false
    }
    
    /**
     * Returns the current rubberband rectangle as an object.
     * Useful for passing to selection logic.
     */
    function getRect() {
        return { x: root.x, y: root.y, width: root.width, height: root.height }
    }
}
