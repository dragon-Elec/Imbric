"""
ProgressOverlay - Non-blocking file operation progress indicator.

Nautilus-style overlay that appears at the bottom of the window during
file operations. Features:
- Only shows if operation takes > 500ms (avoids flash for quick ops)
- Non-blocking (no dialog)
- Shows progress bar and cancel button
- Auto-hides on completion
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon


class ProgressOverlay(QFrame):
    """
    A slide-up overlay widget that shows file operation progress.
    Place at the bottom of your main window.
    """
    
    cancelRequested = Signal(str)  # (job_id) for targeted cancel
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Styling
        self.setObjectName("ProgressOverlay")
        self.setStyleSheet("""
            #ProgressOverlay {
                background-color: palette(window);
                border-top: 1px solid palette(mid);
                padding: 8px;
            }
        """)
        
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        # Icon
        self.icon_label = QLabel()
        self.icon_label.setPixmap(QIcon.fromTheme("edit-copy").pixmap(24, 24))
        layout.addWidget(self.icon_label)
        
        # Info section
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        self.title_label = QLabel("Copying files...")
        self.title_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.title_label)
        
        self.detail_label = QLabel("0 / 0 MB")
        self.detail_label.setStyleSheet("color: palette(dark);")
        info_layout.addWidget(self.detail_label)
        
        layout.addLayout(info_layout, 1)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setMaximumWidth(300)
        layout.addWidget(self.progress_bar)
        
        # Cancel button
        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(QIcon.fromTheme("process-stop"))
        self.cancel_btn.setToolTip("Cancel")
        self.cancel_btn.setFlat(True)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.cancel_btn)
        
        # State
        self._operation_type = ""
        self._current_job_id = ""  # Track current job for cancel
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._do_show)
        self._pending_show = False
        
        # Start hidden
        self.setVisible(False)
        self.setMaximumHeight(0)
    
    @Slot(str, str, str)
    def onOperationStarted(self, job_id: str, op_type: str, path: str):
        """Called when a file operation starts."""
        self._current_job_id = job_id
        self._operation_type = op_type
        self._pending_show = True
        
        # Set icon based on operation
        icons = {
            "copy": "edit-copy",
            "move": "edit-cut",
            "trash": "user-trash",
            "rename": "edit-rename",
        }
        icon_name = icons.get(op_type, "document-save")
        self.icon_label.setPixmap(QIcon.fromTheme(icon_name).pixmap(24, 24))
        
        # Set title
        titles = {
            "copy": "Copying...",
            "move": "Moving...",
            "trash": "Moving to Trash...",
            "rename": "Renaming...",
        }
        self.title_label.setText(titles.get(op_type, "Working..."))
        self.detail_label.setText("")
        self.progress_bar.setValue(0)
        
        # Delay show by 300ms (balanced)
        self._show_timer.start(300)
    
    @Slot(str, int, int)
    def onOperationProgress(self, job_id: str, current: int, total: int):
        """Called during file operation progress."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            
            mb_current = current / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.detail_label.setText(f"{mb_current:.1f} / {mb_total:.1f} MB")
    
    @Slot(str, str, str)
    def onOperationCompleted(self, op_type: str, path: str, result_data: str):
        """Called when operation completes successfully."""
        self._pending_show = False
        self._show_timer.stop()
        self._do_hide()
    
    @Slot(str, str, str)
    def onOperationError(self, op_type: str, path: str, error: str):
        """Called when operation fails."""
        self._pending_show = False
        self._show_timer.stop()
        
        # Show error briefly
        self.title_label.setText(f"Error: {error}")
        self.detail_label.setText("")
        self.progress_bar.setVisible(False)
        
        # Hide after 3 seconds
        QTimer.singleShot(3000, self._do_hide)
    
    def _do_show(self):
        """Actually show the overlay (called after delay)."""
        if not self._pending_show:
            return
        
        self.setVisible(True)
        self.progress_bar.setVisible(True)
        self.setMaximumHeight(60)
    
    def _do_hide(self):
        """Hide the overlay."""
        self.setVisible(False)
        self.setMaximumHeight(0)
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        if self._current_job_id:
            self.cancelRequested.emit(self._current_job_id)
