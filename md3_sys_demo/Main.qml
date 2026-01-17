import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: root
    width: 800
    height: 600
    padding: 0 // Remove default padding so background fills edge-to-edge

    // --- 0. TYPOGRAPHY ---
    // Inherit the System Font (e.g., Cantarell, Inter, Roboto)
    // This makes the app look "native" immediately.
    // Note: We only set the family to avoid inheriting weird sizes.
    font.family: Qt.application.font.family
    font.pixelSize: Qt.application.font.pixelSize > 0 ? Qt.application.font.pixelSize : 14

    // --- 1. THE BRIDGE ---
    // This looks at your OS theme (GTK/Windows/Mac)
    SystemPalette { 
        id: sysPal 
        colorGroup: SystemPalette.Active 
    }

    // A toggle to compare "Native" vs "Standard Material"
    property bool useSystemColors: true
    
    // DETECT SYSTEM DARK MODE (Fix for "shitty" colors)
    // We must tell Material engine if we are Dark/Light so it calculates text/ripples correctly.
    // Qt automatically emits a signal when this changes.
    readonly property bool isSystemDark: Qt.styleHints.colorScheme === Qt.Dark
    
    // --- 2. MATERIAL OVERRIDES ---
    // A. Set the Base Theme Logic (Light vs Dark)
    // This binding is reactive. When OS changes -> Qt signals -> isSystemDark updates -> Material.theme updates.
    Material.theme: isSystemDark ? Material.Dark : Material.Light

    // B. Map Colors (The Translation)
    // Accent (Buttons, Selection, Focus) -> System Highlight (GTK Accent)
    Material.accent: useSystemColors ? sysPal.highlight : Material.Teal
    
    // Primary (Toolbars, Fab) -> System Highlight
    Material.primary: useSystemColors ? sysPal.highlight : Material.Indigo

    // Background (Window color) -> System Window Color
    // If we are in Dark Mode, sysPal.window is dark. Material.background expects this.
    Material.background: useSystemColors ? sysPal.window : undefined

    // Foreground (Text) -> System Text Color
    Material.foreground: useSystemColors ? sysPal.text : undefined


    // --- UI LAYOUT ---
    
    // Background filler (Material.background handles components, but we need to fill the window)
    Rectangle {
        anchors.fill: parent
        color: Material.background
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: 400
        spacing: 20

        Label {
            text: "Material 3 + System Theme"
            font.pixelSize: 24
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
        }

        // CONTROL PANEL
        Frame {
            Layout.fillWidth: true
            background: Rectangle { 
                color: "transparent"
                border.color: Material.accent
                border.width: 1
                radius: 4
            }
            
            ColumnLayout {
                width: parent.width
                Switch {
                    text: "Use System Palette"
                    checked: root.useSystemColors
                    onCheckedChanged: root.useSystemColors = checked
                }
                Label {
                    text: root.useSystemColors ? "Active: Your Zorin OS Colors" : "Active: Default Material (Teal/Indigo)"
                    color: Material.accent
                    font.bold: true
                }
            }
        }

        // WIDGETS SHOWCASE
        GroupBox {
            title: "Widgets"
            Layout.fillWidth: true
            
            ColumnLayout {
                spacing: 15
                width: parent.width

                Button {
                    text: "Primary Action"
                    highlighted: true
                    Layout.fillWidth: true
                }

                Button {
                    text: "Secondary Action"
                    Layout.fillWidth: true
                }

                TextField {
                    placeholderText: "Type something..."
                    Layout.fillWidth: true
                }

                RowLayout {
                    CheckBox { text: "Check me"; checked: true }
                    RadioButton { text: "Option A"; checked: true }
                }

                Slider {
                    value: 0.7
                    Layout.fillWidth: true
                }

                ProgressBar {
                    value: 0.5
                    Layout.fillWidth: true
                }
            }
        }

        // ICONS SHOWCASE
        GroupBox {
            title: "Native Icons (System Theme)"
            Layout.fillWidth: true
            
            RowLayout {
                width: parent.width
                spacing: 10
                
                // Uses standard freedesktop icon names
                // "flat: true" removes the gray background pill
                Button { icon.name: "folder"; text: "Open"; flat: true; Layout.fillWidth: true }
                Button { icon.name: "document-save"; text: "Save"; flat: true; Layout.fillWidth: true }
                
                // "highlighted: true" keeps the colored pill for emphasis
                Button { icon.name: "edit-delete"; text: "Delete"; highlighted: true; Material.accent: Material.Red; Layout.fillWidth: true }
                
                ToolButton { icon.name: "go-home" }
                ToolButton { icon.name: "preferences-system" }
            }
        }
    }
}
