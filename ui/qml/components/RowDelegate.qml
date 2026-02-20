import QtQuick
import QtQuick.Layouts
// import components as Components // Not needed if in same module

Row {
    id: rowDelegateRoot
    spacing: 10
    
    // Model data passed from ListView
    property var rowData: modelData
    
    // Constants (Bound to RowBuilder if possible, or passed via context)
    property int imageHeight: 200 
    
    readonly property int footerHeight: 36
    height: imageHeight + footerHeight

    // Services (Injected from JustifiedView)
    property var bridge
    property var selModel
    property var rowBuilder // Injected
    property var view // Renamed from root to avoid ambiguity

    Repeater {
        model: rowDelegateRoot.rowData
        
        // Use wrapper Item to capture modelData scope
        delegate: Item {
            id: itemWrapper
            property var itemData: modelData  // Capture here
            property int itemIndex: index     // Capture index too
            
            width: childrenRect.width
            height: childrenRect.height
            
            FileDelegate {
                id: fileDelegate
                
                // 1. DATA BINDINGS (from captured itemData)
                path: itemWrapper.itemData.path || ""
                name: itemWrapper.itemData.name || ""
                isDir: itemWrapper.itemData.isDir || false
                isVisual: itemWrapper.itemData.isVisual || false
                iconName: itemWrapper.itemData.iconName || ""
                modelWidth: itemWrapper.itemData.width || 0
                modelHeight: itemWrapper.itemData.height || 0
                index: itemWrapper.itemIndex
                
                // 2. VIEW LAYOUT
                imageHeight: rowDelegateRoot.imageHeight
                
                columnWidth: {
                    // Calculate width from aspect ratio
                    let aspect = (modelWidth > 0 && modelHeight > 0) ? (modelWidth / modelHeight) : 1.0
                    let calculated = aspect * rowDelegateRoot.imageHeight
                    
                    // Cap cell width at thumbnail's longest edge (0 = no cap for icons/vectors)
                    let cap = Math.max(itemWrapper.itemData.thumbnailWidth || 0, itemWrapper.itemData.thumbnailHeight || 0)
                    return cap > 0 ? Math.min(calculated, cap) : calculated
                }
                
                // Pass thumbnail caps to FileDelegate for letterboxing
                thumbnailMaxWidth: itemWrapper.itemData.thumbnailWidth || 0
                thumbnailMaxHeight: itemWrapper.itemData.thumbnailHeight || 0
                
                // Pre-computed thumbnail URL (no Python calls during scroll)
                thumbnailUrl: itemWrapper.itemData.thumbnailUrl || ""
                
                // 3. STATE PROPS
                selected: (rowDelegateRoot.view && rowDelegateRoot.view.currentSelection) 
                          ? rowDelegateRoot.view.currentSelection.indexOf(path) !== -1 
                          : false
                          
                renamingPath: (rowDelegateRoot.view) ? rowDelegateRoot.view.pathBeingRenamed : ""
                
                cutPaths: rowDelegateRoot.bridge ? rowDelegateRoot.bridge.cutPaths : []
                
                // Services
                bridge: rowDelegateRoot.bridge
                selModel: rowDelegateRoot.selModel
                rowBuilder: rowDelegateRoot.rowBuilder
                
                // Handle rename events
                onRenameCommitted: (newName) => { if(rowDelegateRoot.view) rowDelegateRoot.view.pathBeingRenamed = "" }
                onRenameCancelled: { if(rowDelegateRoot.view) rowDelegateRoot.view.pathBeingRenamed = "" }

                // 4. INTERACTIONS
                onClicked: (button, modifiers) => {
                    console.log("[JustifiedView] Delegate Clicked:", path)
                    if (button === Qt.RightButton) {
                        if (!selModel.isSelected(path)) selModel.select(path)
                        bridge.showContextMenu(selModel.selection)
                    } else {
                        var ctrl = (modifiers & Qt.ControlModifier)
                        var shift = (modifiers & Qt.ShiftModifier)
                        selModel.handleClick(path, ctrl, shift, rowBuilder.getAllItems())
                    }
                }
                onDoubleClicked: {
                    console.log("[JustifiedView] Delegate DoubleClicked:", path)
                    if (bridge) bridge.openPath(path)
                }
            }
        }
    }
}
