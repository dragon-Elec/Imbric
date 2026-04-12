from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, 
    QSizePolicy, QApplication
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

class CustomHeader(QWidget):
    """
    Experimental CSD Header.
     Wraps the NavigationBar and adds window controls.
    """
    def __init__(self, navigation_bar, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 5, 0)
        self.layout.setSpacing(0)
        
        # Set height to mimic title bar
        self.setFixedHeight(50)
        
        # 1. Add Navigation Bar (it expands)
        self.layout.addWidget(navigation_bar)
        
        # 2. Window Controls
        self._setup_window_controls()
        
    def _setup_window_controls(self):
        # Separator
        line = QWidget()
        line.setFixedWidth(1)
        line.setStyleSheet("background-color: #444; margin: 10px 0;")
        self.layout.addWidget(line)

        # Minimize
        self.btn_min = QToolButton()
        self.btn_min.setIcon(QIcon.fromTheme("window-minimize"))
        self.btn_min.clicked.connect(self._minimize_window)
        self.layout.addWidget(self.btn_min)

        # Maximize/Restore
        self.btn_max = QToolButton()
        self.btn_max.setIcon(QIcon.fromTheme("window-maximize"))
        self.btn_max.clicked.connect(self._toggle_maximize)
        self.layout.addWidget(self.btn_max)

        # Close
        self.btn_close = QToolButton()
        self.btn_close.setIcon(QIcon.fromTheme("window-close"))
        self.btn_close.setStyleSheet("QToolButton:hover { background-color: #e81123; }")
        self.btn_close.clicked.connect(self._close_window)
        self.layout.addWidget(self.btn_close)

    def _minimize_window(self):
        if self.window(): self.window().showMinimized()

    def _close_window(self):
        if self.window(): self.window().close()

    def _toggle_maximize(self):
        win = self.window()
        if not win: return
        
        if win.isMaximized():
            win.showNormal()
            self.btn_max.setIcon(QIcon.fromTheme("window-maximize"))
        else:
            win.showMaximized()
            self.btn_max.setIcon(QIcon.fromTheme("view-restore"))

    # --- CSD Dragging ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.window()
            if win.windowHandle():
                win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
