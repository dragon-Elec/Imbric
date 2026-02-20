import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import components as Components
// import views as Views - Same directory, no import needed

Item {
    id: root
    
    // Dependencies injected from Python
    // property var tabModel (Implicitly available via context property "tabModel")
    // property var tabManager (Implicitly available via context property "tabManager")

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
            Layout.preferredHeight: 34 // Reduced from 36 to match removed margin
            z: 1 // Ensure TabBar is above content for mask effects
            
            model: tabModel
            currentIndex: tabManager ? tabManager.currentIndex : 0
            
            onAddClicked: if (tabManager) tabManager.add_tab("")
            onTabClosed: (index) => { if (tabManager) tabManager.close_tab(index) }
            
            // Two-way binding for current index
            onCurrentIndexChanged: {
                if (tabManager && tabManager.currentIndex !== currentIndex) {
                    tabManager.currentIndex = currentIndex
                }
            }
        }
        
        // 2. Content Stack
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
                    
                    // "controller" role from TabListModel
                    property var tabController: model.controller 
                    
                    // Provide the view
                    JustifiedView {
                        anchors.fill: parent
                        
                        // Dependency Injection:
                        // Pass the per-tab objects to the view
                        tabController: tabWrapper.tabController
                        rowBuilder: tabWrapper.tabController.rowBuilder
                        fileScanner: tabWrapper.tabController.fileScanner
                        bridge: tabWrapper.tabController.appBridge
                        
                        // Listen for selection requests from backend (e.g. after paste)
                        Connections {
                            target: tabWrapper.tabController
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
