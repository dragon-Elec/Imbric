import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    title: qsTr("Advanced Transfer Options")
    modal: true
    standardButtons: Dialog.Cancel | Dialog.Ok
    width: 450
    
    // --- DI from App ---
    property var capabilities: ({})
    property string mode: "copy" // "copy" or "move"
    
    // --- Result Policy ---
    property bool skipPreflight: false
    property var policy: ({
        "collision_mode": "prompt",
        "always_copy": true,
        "compare_size": true,
        "compare_mtime": true,
        "mtime_window_ms": 2000
    })

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // 1. Execution Strategy
        GroupBox {
            title: qsTr("Execution Strategy")
            Layout.fillWidth: true
            
            ColumnLayout {
                anchors.fill: parent
                RadioButton {
                    id: jitRadio
                    text: qsTr("Just-In-Time (Recommended for MTP/Network)")
                    checked: true
                    onCheckedChanged: if(checked) root.skipPreflight = true
                }
                Label {
                    text: qsTr("Resolve conflicts as they occur. Minimal upfront lag.")
                    color: "gray"
                    font.pixelSize: 11
                    Layout.leftMargin: 28
                }
                
                RadioButton {
                    id: preflightRadio
                    text: qsTr("Pre-flight Assessment (Upfront)")
                    enabled: capabilities.supports_preflight !== false
                    onCheckedChanged: if(checked) root.skipPreflight = false
                }
                Label {
                    text: capabilities.supports_preflight === false ? 
                          qsTr("Not recommended for this device (High Latency)") :
                          qsTr("Assess all conflicts before starting.")
                    color: "gray"
                    font.pixelSize: 11
                    Layout.leftMargin: 28
                }
            }
        }

        // 2. Conflict Policy
        GroupBox {
            title: qsTr("Conflict Resolution")
            Layout.fillWidth: true
            
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Label { text: qsTr("On name collision:") }
                    ComboBox {
                        id: collisionCombo
                        Layout.fillWidth: true
                        model: [
                            { text: qsTr("Ask me (Prompt)"), value: "prompt" },
                            { text: qsTr("Always Overwrite"), value: "overwrite" },
                            { text: qsTr("Always Rename"), value: "rename" },
                            { text: qsTr("Skip existing"), value: "skip" }
                        ]
                        textRole: "text"
                        currentIndex: 0
                        onActivated: root.policy.collision_mode = model[currentIndex].value
                    }
                }
            }
        }

        // 3. Smart Comparison (Rsync-lite)
        GroupBox {
            title: qsTr("Smart Comparison (Rsync-lite)")
            Layout.fillWidth: true
            checkable: true
            checked: false
            onCheckedChanged: root.policy.always_copy = !checked
            
            ColumnLayout {
                anchors.fill: parent
                enabled: parent.checked

                CheckBox {
                    id: sizeCheck
                    text: qsTr("Compare file size")
                    checked: true
                    onCheckedChanged: root.policy.compare_size = checked
                }
                CheckBox {
                    id: timeCheck
                    text: qsTr("Compare modification time")
                    checked: true
                    enabled: capabilities.reliable_mtime !== false
                    onCheckedChanged: root.policy.compare_mtime = checked
                }
                
                RowLayout {
                    Layout.leftMargin: 28
                    enabled: timeCheck.checked
                    Label { text: qsTr("Time window:") }
                    SpinBox {
                        id: windowSpin
                        from: 0
                        to: 10000
                        value: 2000
                        stepSize: 500
                        editable: true
                        onValueChanged: root.policy.mtime_window_ms = value
                    }
                    Label { text: qsTr("ms") }
                }
                
                Label {
                    visible: capabilities.reliable_mtime === false
                    text: qsTr("Warning: Timestamps on this device may be unreliable.")
                    color: "#d03e3e"
                    font.pixelSize: 11
                    font.italic: true
                }
            }
        }
    }
    
    onAccepted: {
        // Validation/Finalization
        console.log("[AdvancedTransfer] Starting with skipPreflight=" + skipPreflight)
    }
}
