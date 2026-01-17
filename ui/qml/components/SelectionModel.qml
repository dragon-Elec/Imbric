import QtQuick

/**
 * SelectionModel.qml
 * 
 * Manages a list of selected items (by key/id).
 * Matches the concept of Qt's QItemSelectionModel but simplified for QML.
 * 
 * Usage:
 *   SelectionModel {
 *       id: selectionModel
 *   }
 *   
 *   // In your delegate:
 *   property bool selected: selectionModel.isSelected(model.id)
 *   
 *   // On click:
 *   selectionModel.toggle(model.id, mouse.modifiers & Qt.ControlModifier)
 */
QtObject {
    id: root
    
    // --- Selection State ---
    // We store selected items as an array of keys (strings or numbers).
    // QML auto-generates 'onSelectionChanged' signal for this property.
    property var selection: []
    
    // --- API ---
    
    /**
     * Checks if a key is currently selected.
     * @param key - The item identifier (e.g., path, id)
     * @returns bool
     */
    function isSelected(key) {
        return selection.indexOf(key) !== -1
    }
    
    /**
     * Selects a single item, clearing any previous selection.
     * @param key - The item to select
     */
    function select(key) {
        selection = [key]
    }
    
    /**
     * Clears all selection.
     */
    function clear() {
        selection = []
    }
    
    /**
     * Toggles an item's selection state.
     * @param key - The item identifier
     * @param multi - If true, preserves existing selection (Ctrl+Click behavior)
     */
    function toggle(key, multi) {
        if (!multi) {
            // Single select mode: Replace selection with this item
            selection = [key]
        } else {
            // Multi select mode: Toggle this item
            var idx = selection.indexOf(key)
            var newSel = selection.slice() // Copy
            if (idx === -1) {
                newSel.push(key)
            } else {
                newSel.splice(idx, 1)
            }
            selection = newSel
        }
    }
    
    /**
     * Selects a range of items (e.g., from RubberBand).
     * @param keys - Array of item identifiers to select
     * @param append - If true, adds to existing selection (Ctrl+Drag behavior)
     */
    function selectRange(keys, append) {
        if (append) {
            // Union with existing
            var newSel = selection.slice()
            for (var i = 0; i < keys.length; i++) {
                if (newSel.indexOf(keys[i]) === -1) {
                    newSel.push(keys[i])
                }
            }
            selection = newSel
        } else {
            // Replace selection
            selection = keys
        }
    }
    
    /**
     * Returns the current selection as an array.
     */
    function getSelection() {
        return selection
    }
    
    /**
     * Returns the number of selected items.
     */
    function count() {
        return selection.length
    }
}
