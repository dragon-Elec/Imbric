import QtQuick
import QtQuick.Controls

// A reusable model-driven GTK Menu that parses Python dictionaries.
GtkMenu {
    id: rootMenu
    
    property var modelData: []
    signal actionTriggered(string actionId)

    // Array to track dynamically created objects to prevent memory leaks
    property var _dynamicObjects: []
    
    // Properties for submenus
    property bool checkable: false
    property bool checked: false
    
    // Exclusive action group for sort-by options (radio button behavior)
    ActionGroup {
        id: sortKeyGroup
    }
    
    // Rebuild the menu when the data model updates. 
    // We defer the execution using Qt.callLater to allow the Menu time to handle the 
    // click event and close itself before we rip the items out from underneath it.
    onModelDataChanged: Qt.callLater(rebuildMenu)

    function rebuildMenu() {
        // 1. Clear existing items from the visual menu
        while (count > 0) {
            var item = itemAt(0);
            removeItem(item);
        }

        // 2. Clean up memory from previously created dynamic items
        for (let i = 0; i < _dynamicObjects.length; i++) {
            if (_dynamicObjects[i]) {
                _dynamicObjects[i].destroy();
            }
        }
        _dynamicObjects = [];

        if (!modelData) return;

        // 3. Build the new menu items
        for (let i = 0; i < modelData.length; i++) {
            let itemDef = modelData[i];
            
            if (itemDef.type === "separator") {
                let sepComp = Qt.createComponent("GtkMenuSeparator.qml");
                if (sepComp.status === Component.Ready) {
                    let sep = sepComp.createObject(null);
                    rootMenu.addItem(sep);
                    _dynamicObjects.push(sep);
                } else {
                    console.error("Failed to load GtkMenuSeparator:", sepComp.errorString());
                }
            } 
            else if (itemDef.submenu !== undefined) {
                let submenuComp = Qt.createComponent("GtkActionMenu.qml");
                if (submenuComp.status === Component.Ready) {
                    let submenu = submenuComp.createObject(rootMenu, {
                        "title": itemDef.text || "",
                        "modelData": itemDef.submenu,
                        "enabled": itemDef.enabled !== undefined ? itemDef.enabled : true,
                        "checkable": itemDef.checkable !== undefined ? itemDef.checkable : false,
                        "checked": itemDef.checked !== undefined ? itemDef.checked : false
                    });
                    
                    submenu.actionTriggered.connect(rootMenu.actionTriggered);
                    rootMenu.addMenu(submenu);
                    _dynamicObjects.push(submenu);
                } else {
                    console.error("Failed to load nested GtkActionMenu:", submenuComp.errorString());
                }
            } 
            else {
                let action = Qt.createQmlObject(`
                    import QtQuick.Controls
                    Action { property bool isRadio: false }
                `, rootMenu);
                
                action.text = itemDef.text || "";
                if (itemDef.icon) action.icon.name = itemDef.icon;
                if (itemDef.shortcut) action.shortcut = itemDef.shortcut;
                if (itemDef.enabled !== undefined) action.enabled = itemDef.enabled;
                if (itemDef.checkable !== undefined) action.checkable = itemDef.checkable;
                if (itemDef.checked !== undefined) action.checked = itemDef.checked;
                action.isRadio = itemDef.is_radio !== undefined ? itemDef.is_radio : false;
                
                // Exclusive group for sort-by keys (radio button behavior)
                if (itemDef.id && itemDef.id.startsWith("SORT_KEY_")) {
                    sortKeyGroup.addAction(action);
                }
                
                let actionId = itemDef.id || "unknown";
                action.triggered.connect(function() {
                    console.log("[GtkActionMenu] Action triggered:", actionId);
                    rootMenu.actionTriggered(actionId);
                });
                
                rootMenu.addAction(action);
                _dynamicObjects.push(action);
            }
        }
    }
}
