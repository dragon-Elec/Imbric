// Copyright (C) 2022 The Qt Company Ltd.
// SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause

pragma ComponentBehavior: Bound

import QtCore
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

import "." as App

ApplicationWindow {
    id: window
    width: 360
    height: 520
    visible: true
    title: qsTr("Qt Quick Controls")

    //! [orientation]
    readonly property bool portraitMode: !orientationCheckBox.checked || window.width < window.height
    //! [orientation]

    function help() {
        let displayingControl = listView.currentIndex !== -1
        let currentControlName = displayingControl
            ? listView.model.get(listView.currentIndex).title.toLowerCase() : ""
        let url = "https://doc.qt.io/qt-6/"
            + (displayingControl
               ? "qml-qtquick-controls2-" + currentControlName + ".html"
               : "qtquick-controls2-qmlmodule.html");
        Qt.openUrlExternally(url)
    }

    property var builtInStyles: ["Basic", "Fusion", "Imagine", "Material", "Universal"]

    Settings {
        id: settings
        property string style
    }

    Shortcut {
        sequences: ["Esc", "Back"]
        enabled: stackView.depth > 1
        onActivated: navigateBackAction.trigger()
    }

    Shortcut {
        sequence: StandardKey.HelpContents
        onActivated: window.help()
    }

    Action {
        id: navigateBackAction
        icon.name: stackView.depth > 1 ? "back" : "drawer"
        onTriggered: {
            if (stackView.depth > 1) {
                stackView.pop()
                listView.currentIndex = -1
            } else {
                drawer.open()
            }
        }
    }

    Shortcut {
        sequence: "Menu"
        onActivated: optionsMenuAction.trigger()
    }

    Action {
        id: optionsMenuAction
        icon.name: "menu"
        onTriggered: optionsMenu.open()
    }

    header: ToolBar {
        RowLayout {
            spacing: 20
            anchors.fill: parent
            anchors.leftMargin: !window.portraitMode ? drawer.width : undefined

            ToolButton {
                action: navigateBackAction
                visible: window.portraitMode
            }

            Label {
                id: titleLabel
                text: listView.currentItem ? (listView.currentItem as ItemDelegate).text : qsTr("Gallery")
                font.pixelSize: 20
                elide: Label.ElideRight
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                Layout.fillWidth: true
            }

            ToolButton {
                action: optionsMenuAction

                Menu {
                    id: optionsMenu
                    x: parent.width - width
                    transformOrigin: Menu.TopRight

                    Action {
                        text: qsTr("Settings")
                        onTriggered: settingsDialog.open()
                    }
                    Action {
                        text: qsTr("Help")
                        onTriggered: window.help()
                    }
                    Action {
                        text: qsTr("About")
                        onTriggered: aboutDialog.open()
                    }
                }
            }
        }
    }

    Drawer {
        id: drawer

        width: Math.min(window.width, window.height) / 3 * 2
        height: window.height
        modal: window.portraitMode
        interactive: window.portraitMode ? (stackView.depth === 1) : false
        position: window.portraitMode ? 0 : 1
        visible: !window.portraitMode

        ListView {
            id: listView

            focus: true
            currentIndex: 1 // Start at Button Page
            anchors.fill: parent

            model: ListModel {
                ListElement { title: qsTr("BusyIndicator"); source: "pages/BusyIndicatorPage.qml" }
                ListElement { title: qsTr("Button"); source: "pages/ButtonPage.qml" }
                ListElement { title: qsTr("CheckBox"); source: "pages/CheckBoxPage.qml" }
                ListElement { title: qsTr("ComboBox"); source: "pages/ComboBoxPage.qml" }
                ListElement { title: qsTr("DelayButton"); source: "pages/DelayButtonPage.qml" }
                ListElement { title: qsTr("Dial"); source: "pages/DialPage.qml" }
                ListElement { title: qsTr("Dialog"); source: "pages/DialogPage.qml" }
                ListElement { title: qsTr("Delegates"); source: "pages/DelegatePage.qml" }
                ListElement { title: qsTr("Frame"); source: "pages/FramePage.qml" }
                ListElement { title: qsTr("GroupBox"); source: "pages/GroupBoxPage.qml" }
                ListElement { title: qsTr("PageIndicator"); source: "pages/PageIndicatorPage.qml" }
                ListElement { title: qsTr("ProgressBar"); source: "pages/ProgressBarPage.qml" }
                ListElement { title: qsTr("RadioButton"); source: "pages/RadioButtonPage.qml" }
                ListElement { title: qsTr("RangeSlider"); source: "pages/RangeSliderPage.qml" }
                ListElement { title: qsTr("ScrollBar"); source: "pages/ScrollBarPage.qml" }
                ListElement { title: qsTr("ScrollIndicator"); source: "pages/ScrollIndicatorPage.qml" }
                ListElement { title: qsTr("Slider"); source: "pages/SliderPage.qml" }
                ListElement { title: qsTr("SpinBox"); source: "pages/SpinBoxPage.qml" }
                ListElement { title: qsTr("StackView"); source: "pages/StackViewPage.qml" }
                ListElement { title: qsTr("SwipeView"); source: "pages/SwipeViewPage.qml" }
                ListElement { title: qsTr("Switch"); source: "pages/SwitchPage.qml" }
                ListElement { title: qsTr("TabBar"); source: "pages/TabBarPage.qml" }
                ListElement { title: qsTr("TextArea"); source: "pages/TextAreaPage.qml" }
                ListElement { title: qsTr("TextField"); source: "pages/TextFieldPage.qml" }
                ListElement { title: qsTr("ToolTip"); source: "pages/ToolTipPage.qml" }
                ListElement { title: qsTr("Tumbler"); source: "pages/TumblerPage.qml" }
            }

            delegate: ItemDelegate {
                id: delegateItem
                width: ListView.view.width
                text: title
                highlighted: ListView.isCurrentItem

                required property int index
                required property var model
                required property string title
                required property string source

                onClicked: {
                    listView.currentIndex = index
                    stackView.push(source)
                    if (window.portraitMode)
                        drawer.close()
                }
            }

            ScrollIndicator.vertical: ScrollIndicator { }
        }
    }

    StackView {
        id: stackView

        anchors.fill: parent
        anchors.leftMargin: !window.portraitMode ? drawer.width : undefined

        initialItem: "pages/ButtonPage.qml"
    }

    Dialog {
        id: settingsDialog
        x: Math.round((window.width - width) / 2)
        y: Math.round(window.height / 6)
        width: Math.round(Math.min(window.width, window.height) / 3 * 2)
        modal: true
        focus: true
        title: qsTr("Settings")

        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            settings.style = styleBox.displayText
            settingsDialog.close()
        }
        onRejected: {
            styleBox.currentIndex = styleBox.styleIndex
            settingsDialog.close()
        }

        contentItem: ColumnLayout {
            id: settingsColumn
            spacing: 20

            RowLayout {
                spacing: 10

                Label {
                    text: qsTr("Style:")
                }

                ComboBox {
                    id: styleBox
                    property int styleIndex: -1
                    model: window.builtInStyles
                    Component.onCompleted: {
                        styleIndex = find(settings.style, Qt.MatchFixedString)
                        if (styleIndex !== -1)
                            currentIndex = styleIndex
                    }
                    Layout.fillWidth: true
                }
            }

            CheckBox {
                id: orientationCheckBox
                text: qsTr("Enable Landscape")
                checked: false
                Layout.fillWidth: true
            }

            Label {
                text: qsTr("Restart required")
                color: "#e41e25"
                opacity: styleBox.currentIndex !== styleBox.styleIndex ? 1.0 : 0.0
                horizontalAlignment: Label.AlignHCenter
                verticalAlignment: Label.AlignVCenter
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }
    }

    Dialog {
        id: aboutDialog
        modal: true
        focus: true
        title: qsTr("About")
        x: (window.width - width) / 2
        y: window.height / 6
        width: Math.min(window.width, window.height) / 3 * 2
        contentHeight: aboutColumn.height

        Column {
            id: aboutColumn
            spacing: 20

            Label {
                width: aboutDialog.availableWidth
                text: qsTr("The Qt Quick Controls module delivers the next generation user interface controls based on Qt Quick.")
                wrapMode: Label.Wrap
                font.pixelSize: 12
            }

            Label {
                width: aboutDialog.availableWidth
                text: qsTr("In comparison to Qt Quick Controls 1, Qt Quick Controls "
                    + "are an order of magnitude simpler, lighter, and faster.")
                wrapMode: Label.Wrap
                font.pixelSize: 12
            }
        }
    }
}
