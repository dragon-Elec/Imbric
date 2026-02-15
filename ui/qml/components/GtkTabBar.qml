import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    
    // Access System Palette
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }
    
    // Public API
    property alias model: repeater.model
    property alias count: repeater.count
    property alias currentIndex: bar.currentIndex

    signal addClicked()
    signal tabClosed(int index)

    implicitHeight: 36 // Compact standard height
    visible: count > 0 // Auto-hide if empty (or count > 1 per specs)

    // Unified Background for the whole strip (Tabs + Add Button)
    Rectangle {
        anchors.fill: parent
        color: sysPalette.window
        
        // Bottom border (Separation from view)
        Rectangle {
            width: parent.width; height: 1
            // Use a subtle separator color derived from text (works for light & dark)
            color: Qt.alpha(sysPalette.text, 0.15)
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 0
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // The TabBar itself
        TabBar {
            id: bar
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            // Making sure it behaves elastically
            contentWidth: width 
            
            background: null // Background moved to root

            Repeater {
                id: repeater
                model: root.model
                
                GtkTabButton {
                    text: model.title || model.display || ("Tab " + (index + 1))
                    onCloseClicked: root.tabClosed(index)
                    width: bar.width / Math.max(1, bar.count) // Force equal width split? 
                    // Verify: TabBar defaults to contentWidth usually. 
                    // To force equal split in QtQC2, we might need manual binding if not standard.
                    // Actually, standard TabBar just packs them. 
                    // Let's try native behavior first, if it doesn't expand, we add Layout.fillWidth in delegate.
                }
            }
        }

        // Add Button pinned to right
        ToolButton {
            id: addBtn
            icon.name: "list-add-symbolic"
            icon.color: addBtn.hovered ? sysPalette.highlight : sysPalette.text
            text: "+"
            flat: true
            Layout.fillHeight: true
            Layout.preferredWidth: 40
            onClicked: root.addClicked()
        }
    }
}
