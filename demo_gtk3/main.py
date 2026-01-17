import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QMenu, QPushButton, QVBoxLayout, QWidget, QLineEdit, QLabel
from PySide6.QtGui import QAction, QIcon

class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt6 Native GTK3 Demo")
        self.resize(600, 400)

        # 1. Menu Bar (Should look like GNOME Shell menus if integrated)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Open")
        file_menu.addAction("Exit", self.close)

        # 2. Toolbar (Should respect GTK icon theme)
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction("Back")
        toolbar.addAction("Forward")
        
        # 3. Central Widget with Common Controls
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        
        # Label to show active style
        self.style_label = QLabel("Active Style: Unknown")
        layout.addWidget(self.style_label)
        
        # Text Input (Should have native focus ring/selection color)
        inp = QLineEdit()
        inp.setPlaceholderText("Type something natively...")
        layout.addWidget(inp)
        
        # Button (Should match GTK button style)
        btn = QPushButton("Click Me (Native)")
        layout.addWidget(btn)
        
        layout.addStretch()
        self.setCentralWidget(central)
        
        # Check Style
        self.update_style_info()

    def update_style_info(self):
        style_name = QApplication.style().objectName()
        self.style_label.setText(f"Active Qt Style: {style_name}")

if __name__ == "__main__":
    # We DO NOT set style manually here. We let the environment variable decide.
    app = QApplication(sys.argv)
    
    window = DemoWindow()
    window.show()
    
    sys.exit(app.exec())
