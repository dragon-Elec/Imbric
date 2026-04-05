import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtQuick import QQuickView
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QCursor

app = QApplication(sys.argv)
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)

qml = b"""
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    width: 600; height: 400
    
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        Rectangle { color: "red"; Layout.fillWidth: true; Layout.preferredHeight: 40 }
        
        SplitView {
            id: split
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            handle: Rectangle {
                implicitWidth: 7
                color: "magenta"
            }
            Rectangle { SplitView.minimumWidth: 50; width: 100; color: "blue" }
            Rectangle { 
                SplitView.fillWidth: true; color: "green"
                HoverHandler { cursorShape: Qt.PointingHandCursor }
            }
        }
    }
}
"""
import tempfile

with tempfile.NamedTemporaryFile("wb", suffix=".qml", delete=False) as f:
    f.write(qml)
    path = f.name

view.setSource(QUrl.fromLocalFile(path))

window = QWidget()
layout = QVBoxLayout(window)
layout.setContentsMargins(0, 0, 0, 0)
container = QWidget.createWindowContainer(view, window)
layout.addWidget(container)
window.resize(600, 400)
window.show()


def check():
    print("Test running - fresh snapshot test for undo")
    app.quit()


from PySide6.QtCore import QTimer

QTimer.singleShot(1000, check)
app.exec()
