import sys
import os
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl

# Add parent directory to path so we can import from main app's core/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.file_operations import FileOperations
from core.clipboard_manager import ClipboardManager

if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    
    # Add main app's QML path for shared components
    main_app_qml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "qml")
    engine.addImportPath(main_app_qml_path)
    
    # Also add current directory for local imports
    engine.addImportPath(".")
    
    # Instantiate backend modules and expose to QML
    file_ops = FileOperations()
    clipboard = ClipboardManager()
    
    engine.rootContext().setContextProperty("fileOps", file_ops)
    engine.rootContext().setContextProperty("clipboard", clipboard)
    
    engine.load(QUrl.fromLocalFile("Main.qml"))

    if not engine.rootObjects():
        sys.exit(-1)

    sys.exit(app.exec())
