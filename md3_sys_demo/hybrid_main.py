import sys
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QWidget, QVBoxLayout, QSizePolicy
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QIcon, QAction

def main():
    # 1. Force Material Style for the QML part
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Force Fusion so QSS works consistently
    
    # Load Modern QSS Patches
    qss_path = Path(__file__).parent / "modern.qss"
    
    def apply_styles():
        if qss_path.exists():
            with open(qss_path, "r") as f:
                # Re-applying the sheet forces palette() to be re-evaluated
                app.setStyleSheet(f.read())
                
    # Initial Load
    apply_styles()
    
    # Dynamic Reload: Listen for Palette changes (Dark Mode toggle)
    app.paletteChanged.connect(lambda: apply_styles())
            
    app.setApplicationName("Imbric Hybrid Demo")
    app.setOrganizationName("Gemini")

    # 2. The Native Window
    window = QMainWindow()
    window.resize(900, 700)
    window.setWindowTitle("Hybrid: Native Shell + Material View")

    # 3. Native Toolbar (Qt Widgets)
    toolbar = QToolBar("Main Toolbar")
    toolbar.setMovable(False)
    # Force text beside icons or under, depending on pref. Standard is usually beside.
    toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    window.addToolBar(toolbar)

    # Add Standard Actions
    # "QIcon.fromTheme" grabs the actual SVG from your Zorin OS icon theme
    # We use standard names: folder-open, document-save, edit-delete
    act_open = QAction(QIcon.fromTheme("folder-open"), "Open", window)
    act_save = QAction(QIcon.fromTheme("document-save"), "Save", window)
    act_del  = QAction(QIcon.fromTheme("edit-delete"), "Delete", window)
    act_sys  = QAction(QIcon.fromTheme("preferences-system"), "Settings", window)

    toolbar.addAction(act_open)
    toolbar.addAction(act_save)
    toolbar.addSeparator()
    toolbar.addAction(act_del)
    
    # Spacer widget for toolbar to push Settings to the right
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    toolbar.addWidget(spacer)
    toolbar.addAction(act_sys)

    # 4. The QML Bridge (QQuickWidget)
    # We use QQuickWidget to embed QML inside this QMainWindow
    qml_widget = QQuickWidget()
    qml_widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
    
    qml_path = Path(__file__).parent / "Main.qml"
    qml_widget.setSource(QUrl.fromLocalFile(str(qml_path)))

    if qml_widget.status() == QQuickWidget.Error:
        for err in qml_widget.errors():
            print(err.toString())
        sys.exit(-1)

    window.setCentralWidget(qml_widget)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
