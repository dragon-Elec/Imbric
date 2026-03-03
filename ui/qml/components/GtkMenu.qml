import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Controls.impl
import QtQuick.Controls.Material as M

// A lean, high-fidelity GTK/Adwaita mimic using the unopinionated Basic style engine.
Menu {
    id: root
    
    // --- State & Themes ---
    SystemPalette { id: sysPalette; colorGroup: SystemPalette.Active }
    readonly property bool isDark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    
    // --- Layout Properties ---
    property bool showArrow: false
    property Item targetItem: null
    property int minimumMenuWidth: 180
    
    // Scale-based pointer positioning logic
    property real arrowPosition: {
        if (!targetItem || !showArrow) return 0.5;
        let pos = targetItem.mapToItem(root.contentItem, targetItem.width/2, 0).x / root.width;
        return Math.max(0.1, Math.min(0.9, pos));
    }
    
    // Automatic Width discovery across delegates
    property real calculatedMenuWidth: {
        let maxW = 0;
        for (let i = 0; i < count; ++i) {
            let it = itemAt(i);
            if (it && it.implicitWidth > maxW) maxW = it.implicitWidth;
        }
        return Math.max(maxW, minimumMenuWidth);
    }
    
    // --- Visual Styling (Lean) ---
    topPadding: 6; bottomPadding: 6
    transformOrigin: Item.Top
    enter: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 100 }
        NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: 150; easing.type: Easing.OutQuint }
    }}
    exit: Transition { ParallelAnimation {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 }
        NumberAnimation { property: "scale"; from: 1; to: 0.95; duration: 100 }
    }}
    
    background: Item {
        implicitWidth: root.calculatedMenuWidth; implicitHeight: 40; opacity: 0.98
        
        // NATIVE A11Y: Explicit popup menu role for screen readers
        // Placed here because 'Menu' is a Popup, not an Item.
        Accessible.role: Accessible.PopupMenu
        
        // OPTIMIZATION: MultiEffect (Qt 6.5+) for single-pass GPU shadows
        MultiEffect {
            anchors.fill: bgRect
            source: bgRect
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, root.isDark ? 0.45 : 0.12)
            shadowBlur: root.isDark ? 1.0 : 0.8
            shadowVerticalOffset: 4
            opacity: parent.opacity
        }
        
        Rectangle {
            id: bgRect; anchors.fill: parent; radius: 12; border.width: 1
            color: root.isDark 
                ? Qt.darker(sysPalette.window, 1.4) 
                : Qt.tint("#ffffff", Qt.alpha(sysPalette.highlight, 0.03))
            border.color: root.isDark ? "#484848" : "#e0e0e0"
        }
        
        Canvas {
            id: arrowCanvas; visible: root.showArrow; width: 16; height: 9; y: -8
            x: (parent.width * root.arrowPosition) - 8
            onPaint: {
                let ctx = getContext("2d"); ctx.reset();
                ctx.beginPath(); ctx.moveTo(0, 9); ctx.lineTo(8, 0); ctx.lineTo(16, 9); ctx.closePath();
                ctx.fillStyle = bgRect.color; ctx.fill();
                ctx.lineWidth = 1; ctx.strokeStyle = bgRect.border.color;
                ctx.beginPath(); ctx.moveTo(0, 9); ctx.lineTo(8, 0); ctx.lineTo(16, 9); ctx.stroke();
            }
            Connections { target: root; function onIsDarkChanged() { arrowCanvas.requestPaint() } }
        }
    }

    delegate: GtkMenuItem {}

    // --- Inline Component Delegate (The heavy lifter) ---
    component GtkMenuItem : MenuItem {
        id: item
        implicitHeight: 32; padding: 0; leftPadding: 0; rightPadding: 0; indicator: null
        
        // NATIVE A11Y: Explicit text mapping for screen reader
        Accessible.role: Accessible.MenuItem
        Accessible.name: item.text
        
        arrow: Canvas {
            x: parent.width - 20; y: 11; width: 5; height: 10; visible: item.subMenu
            onPaint: {
                let ctx = getContext("2d"); ctx.fillStyle = item.enabled ? sysPalette.text : Qt.alpha(sysPalette.text, 0.4);
                ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(5, 5); ctx.lineTo(0, 10); ctx.closePath(); ctx.fill();
            }
        }

        contentItem: Item {
            implicitWidth: contentRow.implicitWidth + 32 + (item.action && item.action.shortcut ? 60 : 0) + (item.subMenu ? 24 : 0)
            
            Row {
                id: contentRow; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                spacing: (check.visible || iconItem.visible) ? 12 : 0; leftPadding: 12
                
                M.CheckBox {
                    id: check; visible: item.checkable; checked: item.checked
                    enabled: item.enabled; focusPolicy: Qt.NoFocus
                    padding: 0; leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
                    width: visible ? indicator.width : 0
                    M.Material.theme: root.isDark ? M.Material.Dark : M.Material.Light
                    M.Material.accent: sysPalette.highlight
                }
                
                IconImage {
                    id: iconItem
                    visible: item.icon.name !== ""
                    width: visible ? 16 : 0; height: 16
                    anchors.verticalCenter: parent.verticalCenter
                    name: item.icon.name
                    // ASKD Hybrid Strategy: Tint symbolics, preserve full-color
                    color: name.endsWith("-symbolic") ? sysPalette.text : "transparent"
                    opacity: item.enabled ? 1.0 : 0.4
                    
                    Behavior on width { NumberAnimation { duration: 100 } }
                }

                Text {
                    text: item.text; font: item.font; color: sysPalette.text
                    opacity: item.enabled ? 1.0 : 0.4; anchors.verticalCenter: parent.verticalCenter
                }
            }
            
            Text {
                text: item.action && item.action.shortcut ? item.action.shortcut.toString() : ""
                font: item.font; color: sysPalette.text; opacity: 0.5
                anchors.right: parent.right; anchors.rightMargin: item.subMenu ? 24 : 12
                anchors.verticalCenter: parent.verticalCenter; visible: text !== ""
            }
        }

        background: Rectangle {
            anchors.fill: parent; anchors.margins: 4; radius: 6
            color: sysPalette.highlight; opacity: item.highlighted ? (root.isDark ? 0.19 : 0.25) : 0.0
            Behavior on opacity { NumberAnimation { duration: 50 } }
        }
    }
}
