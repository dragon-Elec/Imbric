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
    property var selection: []
    
    // Anchor for Shift+Click range selection
    property string anchorPath: ""
    
    /**
     * Handles a click with modifier support.
     * Matches Nautilus / Windows Explorer behavior:
     *   - Click:            Select single, clear rest
     *   - Ctrl+Click:       Toggle item, keep rest
     *   - Shift+Click:      Select range [anchor → target], clear rest
     *   - Ctrl+Shift+Click: ADD range [anchor → target] to current selection
     *
     * @param path - The clicked item
     * @param ctrl - Ctrl key is held (bitmask, truthy if held)
     * @param shift - Shift key is held (bitmask, truthy if held)
     * @param allItems - Array of all items in order (from ColumnSplitter.getAllItems())
     */
    function handleClick(path, ctrl, shift, allItems) {
        var ctrlHeld = !!ctrl
        var shiftHeld = !!shift
        
        if (shiftHeld && anchorPath) {
            // Shift+Click or Ctrl+Shift+Click: Range selection
            var range = _computeRange(anchorPath, path, allItems)
            
            if (ctrlHeld) {
                // Ctrl+Shift: ADD range to existing selection (union)
                var newSel = selection.slice()
                for (var i = 0; i < range.length; i++) {
                    if (newSel.indexOf(range[i]) === -1) {
                        newSel.push(range[i])
                    }
                }
                selection = newSel
            } else {
                // Shift only: REPLACE selection with range
                selection = range
            }
            // Note: Do NOT update anchorPath on Shift+Click (anchor stays fixed)
            
        } else if (ctrlHeld) {
            // Ctrl+Click: Toggle this item, keep everything else
            var idx = selection.indexOf(path)
            var newSel = selection.slice()
            if (idx === -1) {
                newSel.push(path)
            } else {
                newSel.splice(idx, 1)
            }
            selection = newSel
            anchorPath = path // Update anchor for future Shift+Clicks
            
        } else {
            // Normal Click: Single select, clear rest
            anchorPath = path
            selection = [path]
        }
    }
    
    /**
     * Computes the range of paths between start and end (inclusive).
     * @private
     */
    function _computeRange(startPath, endPath, allItems) {
        if (!allItems || allItems.length === 0) return [endPath]
        
        var startIdx = -1, endIdx = -1
        for (var i = 0; i < allItems.length; i++) {
            if (allItems[i].path === startPath) startIdx = i
            if (allItems[i].path === endPath) endIdx = i
        }
        
        if (startIdx === -1 || endIdx === -1) return [endPath]
        
        // Ensure startIdx <= endIdx
        if (startIdx > endIdx) {
            var tmp = startIdx
            startIdx = endIdx
            endIdx = tmp
        }
        
        var range = []
        for (var j = startIdx; j <= endIdx; j++) {
            range.push(allItems[j].path)
        }
        return range
    }
    
    /**
     * Selects range from anchor to target.
     * @deprecated Use handleClick with shift=true instead.
     */
    function selectToAnchor(targetPath, allItems) {
        if (!anchorPath || !allItems || allItems.length === 0) {
            selection = [targetPath]
            anchorPath = targetPath
            return
        }
        selection = _computeRange(anchorPath, targetPath, allItems)
    }
    
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
     * Clears all selection AND resets anchor.
     */
    function clear() {
        selection = []
        anchorPath = "" // Reset anchor so next Shift+Click acts as normal click
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
