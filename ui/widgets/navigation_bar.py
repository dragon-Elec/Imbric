from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, 
    QLineEdit, QSizePolicy
)
from PySide6.QtGui import QIcon, QKeySequence, QAction
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtWidgets import QToolTip


from gi.repository import Gio

class NavigationBar(QWidget):
    """
    Unified Navigation Bar containing:
    - Up Button
    - Path/Address Bar
    - Zoom Controls
    """
    
    # Signals to communicate with MainWindow/Controller
    navigateRequested = Signal(str)  # Path
    zoomChanged = Signal(int)        # Delta (+1/-1)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)  # Slight padding
        self.layout.setSpacing(5)
        self._setup_ui()
        
    def _setup_ui(self):
        # 1. Up Button
        self.btn_up = QToolButton(self)
        self.btn_up.setIcon(QIcon.fromTheme("go-up"))
        self.btn_up.setToolTip("Go Up")
        self.btn_up.clicked.connect(self._on_up_clicked)
        self.layout.addWidget(self.btn_up)
        
        # 2. Path Bar
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("PathBar")
        self.path_edit.setPlaceholderText("Enter path...")
        self.path_edit.returnPressed.connect(self._on_path_submitted)
        self.layout.addWidget(self.path_edit)
        
        # Spacer
        # In a QHBoxLayout, we can just let things expand, but let's be explicit
        # if we want the path bar to take available space.
        # Actually QLineEdit usually expands.
        
        # 3. Zoom Controls
        self._setup_zoom_controls()
        
    def _setup_zoom_controls(self):
        zoom_widget = QWidget()
        zoom_layout = QHBoxLayout(zoom_widget)
        zoom_layout.setSpacing(0)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        
        # Zoom Out
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setIcon(QIcon.fromTheme("zoom-out"))
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.btn_zoom_out.setAutoRaise(True)
        self.btn_zoom_out.clicked.connect(lambda: self.zoomChanged.emit(1))
        
        # Zoom In
        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setIcon(QIcon.fromTheme("zoom-in"))
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl+=)")
        self.btn_zoom_in.setAutoRaise(True)
        self.btn_zoom_in.clicked.connect(lambda: self.zoomChanged.emit(-1))
        
        zoom_layout.addWidget(self.btn_zoom_out)
        zoom_layout.addWidget(self.btn_zoom_in)
        
        self.layout.addWidget(zoom_widget)
        
    def set_path(self, path: str):
        """Update the path bar text silently."""
        self.path_edit.setText(path)
        
    def focus_path(self):
        """Focus the path bar and select all text."""
        self.path_edit.setFocus()
        self.path_edit.selectAll()
        
    @Slot()
    def _on_path_submitted(self):
        path = self.path_edit.text().strip()
        
        if not path:
            return
            
        self.navigateRequested.emit(path)
            
    @Slot(str)
    def showError(self, error_msg: str):
        path = self.path_edit.text()
        QToolTip.showText(
            self.path_edit.mapToGlobal(self.path_edit.rect().bottomLeft()),
            f"⚠ {error_msg}",
            self.path_edit,
            self.path_edit.rect(),
            2000
        )
        
        # Visual feedback
        original_style = self.path_edit.styleSheet()
        self.path_edit.setStyleSheet("QLineEdit { border: 2px solid #d32f2f; }")
        
        QTimer.singleShot(1500, lambda: self.path_edit.setStyleSheet(original_style))
        
    @Slot()
    def _on_up_clicked(self):
        # We need the current path to calculate 'Up'
        # But this component doesn't know 'current path' unless we store it.
        # Better: emit a signal "upRequested" or just handle "navigate" logic in parent?
        # Let's emit a signal specific to 'Up' or handle logic here?
        # To be purely dumb, it should emit 'upRequested'.
        # But we can calculate parent of text in path bar?
        current = self.path_edit.text()
        if current:
            try:
                gfile = Gio.File.parse_name(current)
                parent = gfile.get_parent()
                if parent:
                    parent_path = parent.get_path() or parent.get_uri()
                    self.navigateRequested.emit(parent_path)
            except Exception:
                pass
