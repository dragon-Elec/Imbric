import sys
import os
from pathlib import Path

# Important: Use QApplication for better desktop integration (GTK colors)
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtCore import QUrl
from PySide6.QtQuickControls2 import QQuickStyle

def main():
    # 1. Force Material Style
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
    QQuickStyle.setStyle("Material")

    # 2. Use QApplication to grab GTK/System palette correctly
    app = QApplication(sys.argv)
    app.setApplicationName("MD3 System Palette Demo")
    app.setOrganizationName("Gemini")

    # 3. Setup QQuickView
    view = QQuickView()
    view.setTitle("Material 3 + System Palette")
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    
    # Load QML
    qml_path = Path(__file__).parent / "Main.qml"
    view.setSource(QUrl.fromLocalFile(str(qml_path)))
    
    if view.status() == QQuickView.Error:
        print("Error loading QML:")
        for error in view.errors():
            print(error.toString())
        sys.exit(-1)

    view.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
