import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import components as Components
// import views as Views - Same directory, no import needed

Item {
    id: root
    
    // Dependencies injected from Python
    // property var tabModel (Implicitly available via context property "tabModel")
    // property var shellManager (Implicitly available via context property "shellManager")

    // Access System Palette
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }

    // Bind Material Style to System Palette (Matches TabBarShowcase.qml)
    Material.accent: sysPalette.highlight
    Material.primary: sysPalette.highlight

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // 1. Tab Bar
        Components.GtkTabBar {
            id: tabBar
            Layout.fillWidth: true
            Layout.preferredHeight: 25 // Compact standard height
            z: 1 // Ensure TabBar is above content for mask effects
            
            model: tabModel
            currentIndex: shellManager ? shellManager.currentIndex : 0
            
            onAddClicked: if (shellManager) shellManager.add_tab("")
            onTabClosed: (index) => { if (shellManager) shellManager.close_tab(index) }
            
            // Two-way binding for current index
            onCurrentIndexChanged: {
                if (shellManager && shellManager.currentIndex !== currentIndex) {
                    shellManager.currentIndex = currentIndex
                }
            }
        }
        
        // 3. Content Stack
        StackLayout {
            id: contentStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            currentIndex: tabBar.currentIndex
            
            // Dynamic instantiation of views based on the model
            Repeater {
                model: tabModel
                
                // The Delegate acts as the wrapper for each tab's content
                // It injects the specific controller for that tab into the view
                Item {
                    id: tabWrapper
                    
                    // "paneContext" role from TabListModel
                    property var paneContext: model.paneContext 
                    
                    // Provide the view
                    JustifiedView {
                        anchors.fill: parent
                        
                        // Dependency Injection:
                        // Pass the per-tab objects to the view
                        paneContext: tabWrapper.paneContext
                        rowBuilder: tabWrapper.paneContext.rowBuilder
                        fileScanner: tabWrapper.paneContext.fileScanner
                        bridge: tabWrapper.paneContext.appBridge
                        
                        // Listen for selection requests from backend (e.g. after paste)
                        Connections {
                            target: tabWrapper.paneContext
                            function onSelectPathsRequested(paths) {
                                selectPaths(paths)
                            }
                        }
                    }
                }
            }
        }
    }
}
