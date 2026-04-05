import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtQuick import QQuickView
from PySide6.QtCore import QUrl, Qt

app = QApplication(sys.argv)
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)

qml = b"""
import QtQuick
import QtQuick.Controls

Item {
    width: 400; height: 300
    id: root

    TapHandler {
        id: rootHandler
        onTapped: console.log("ROOT TAP")
    }

    Rectangle {
        anchors.centerIn: parent
        width: 200; height: 50
        color: "blue"
        
        TextField {
            anchors.fill: parent
            onActiveFocusChanged: console.log("TextField Focus:", activeFocus)
            
            TapHandler {
                onTapped: console.log("INNER TAP")
            }
        }
    }
}
"""
import tempfile
with tempfile.NamedTemporaryFile("wb", suffix=".qml", delete=False) as f:
    f.write(qml)

view.setSource(QUrl.fromLocalFile(f.name))
view.show()

# No automatic quit, let user manually test if they want or just run it to see logs
from PySide6.QtCore import QTimer
QTimer.singleShot(5000, app.quit)
app.exec()
