import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import components as Components  // Shared library from ui/qml/components/

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 800
    height: 600
    title: "Selection Library Demo"

    // --- MODELS ---
    ListModel {
        id: fileModel
        ListElement { name: "Photo_1.jpg"; color: "#FF5733"; h: 150 }
        ListElement { name: "Photo_2.jpg"; color: "#33FF57"; h: 200 }
        ListElement { name: "Photo_3.jpg"; color: "#3357FF"; h: 120 }
        ListElement { name: "Photo_4.jpg"; color: "#F3FF33"; h: 180 }
        ListElement { name: "Photo_5.jpg"; color: "#33FFFF"; h: 160 }
        ListElement { name: "Photo_6.jpg"; color: "#FF33FF"; h: 140 }
        ListElement { name: "Photo_7.jpg"; color: "#FFFF33"; h: 190 }
        ListElement { name: "Photo_8.jpg"; color: "#3333FF"; h: 130 }
    }

    // --- LIBRARY COMPONENTS ---
    Components.SelectionModel {
        id: selectionModel
    }

    // --- SYSTEM PALETTE ---
    SystemPalette { id: activePalette; colorGroup: SystemPalette.Active }

    // --- ROOT CONTAINER ---
    Item {
        id: rootContainer
        anchors.fill: parent
        
        // Layer 1: Content (Flickable with items)
        Flickable {
            id: flickable
            anchors.fill: parent
            contentHeight: flowLayout.height
            contentWidth: width
            clip: true

            Flow {
                id: flowLayout
                width: parent.width
                spacing: 10
                padding: 10

                Repeater {
                    id: repeater
                    model: fileModel
                    
                    delegate: Item {
                        id: delegateItem
                        width: (flickable.width / 4) - 20
                        height: model.h

                        readonly property bool selected: selectionModel.isSelected(model.name)

                        Rectangle {
                            anchors.fill: parent
                            color: delegateItem.selected ? activePalette.highlight : model.color
                            border.width: delegateItem.selected ? 3 : 0
                            border.color: activePalette.highlightedText

                            Text {
                                anchors.centerIn: parent
                                text: model.name
                                color: delegateItem.selected ? activePalette.highlightedText : "black"
                            }
                        }

                        // Item Click Handler
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            // CRITICAL: Do not propagate - items consume their own clicks
                            
                            onClicked: (mouse) => {
                                console.log("Item clicked:", model.name)
                                if (mouse.button === Qt.RightButton) {
                                    if (!delegateItem.selected) selectionModel.select(model.name)
                                    contextMenu.popup()
                                } else {
                                    selectionModel.toggle(model.name, (mouse.modifiers & Qt.ControlModifier))
                                }
                            }

                            Menu {
                                id: contextMenu
                                MenuItem { text: "Open"; onTriggered: console.log("Open " + model.name) }
                                MenuItem { text: "Copy"; onTriggered: console.log("Copy " + model.name) }
                                MenuSeparator {}
                                MenuItem { text: "Delete"; onTriggered: console.log("Delete " + model.name) }
                            }
                        }
                    }
                }
            }
        }
        
        // Layer 2: RubberBand Interaction Overlay (ON TOP of Flickable)
        MouseArea {
            id: rubberBandArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            hoverEnabled: false
            
            property point startPoint
            property bool isDragging: false

            onPressed: (mouse) => {
                console.log("RubberBand: Press at", mouse.x, mouse.y)
                startPoint = Qt.point(mouse.x, mouse.y)
                isDragging = false
                // Accept the event - we will track drag
                mouse.accepted = true
            }

            onPositionChanged: (mouse) => {
                // Check drag threshold
                if (!isDragging && (Math.abs(mouse.x - startPoint.x) > 5 || Math.abs(mouse.y - startPoint.y) > 5)) {
                    isDragging = true
                    rubberBand.show()
                    console.log("RubberBand: Drag started")
                }

                if (isDragging) {
                    rubberBand.update(startPoint.x, startPoint.y, mouse.x, mouse.y)
                    
                    // Calculate selection
                    var rect = rubberBand.getRect()
                    var hits = []
                    
                    for (var i = 0; i < repeater.count; i++) {
                        var item = repeater.itemAt(i)
                        if (!item) continue
                        
                        // Map item position to this MouseArea
                        var pos = item.mapToItem(rubberBandArea, 0, 0)
                        
                        // Box intersection check
                        if (rect.x < pos.x + item.width && rect.x + rect.width > pos.x &&
                            rect.y < pos.y + item.height && rect.y + rect.height > pos.y) {
                            hits.push(fileModel.get(i).name)
                        }
                    }
                    
                    selectionModel.selectRange(hits, (mouse.modifiers & Qt.ControlModifier))
                }
            }

            onReleased: (mouse) => {
                console.log("RubberBand: Released. isDragging:", isDragging)
                if (isDragging) {
                    rubberBand.hide()
                    isDragging = false
                } else {
                    // Was a click, not a drag
                    // Clear selection if clicked on empty space
                    selectionModel.clear()
                }
            }
            
            // RubberBand visual
            Components.RubberBand {
                id: rubberBand
            }
        }
    }
}
