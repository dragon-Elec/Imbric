"""
ConflictDialog — File Conflict Resolution Dialog

A reusable dialog for handling file name conflicts during copy/move operations.
Provides Skip/Overwrite/Rename/Cancel options with "Apply to all" support.
"""

from enum import Enum, auto
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from gi.repository import Gio


class ConflictAction(Enum):
    """Result of a conflict resolution dialog."""
    SKIP = auto()       # Don't copy/move this file
    OVERWRITE = auto()  # Replace existing file
    RENAME = auto()     # Auto-generate unique name
    CANCEL = auto()     # Abort entire operation


class ConflictDialog(QDialog):
    """
    Modal dialog asking user how to handle a file name conflict.
    
    Usage:
        dialog = ConflictDialog(parent, src_path, dest_path)
        result = dialog.exec()
        action = dialog.action
        apply_all = dialog.apply_to_all
    """
    
    def __init__(self, parent, src_path: str, dest_path: str):
        super().__init__(parent)
        self.action = ConflictAction.CANCEL
        self.apply_to_all = False
        
        self.setWindowTitle("File Conflict")
        self.setMinimumWidth(450)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Header with icon
        header = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(QIcon.fromTheme("dialog-warning").pixmap(48, 48))
        header.addWidget(icon_label)
        
        title = QLabel("<b>File already exists</b>")
        title.setStyleSheet("font-size: 14px;")
        header.addWidget(title, 1)
        layout.addLayout(header)
        
        # File info
        gfile = Gio.File.parse_name(dest_path)
        filename = gfile.get_basename()
        parent = gfile.get_parent()
        dest_dir = parent.get_path() or parent.get_uri() if parent else ""
        
        info_text = f"""
        <p>A file named <b>"{filename}"</b> already exists in:</p>
        <p style="color: gray; font-size: 11px;">{dest_dir}</p>
        <p>What do you want to do?</p>
        """
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # Apply to all checkbox
        self.apply_all_cb = QCheckBox("Apply this action to all conflicts")
        layout.addWidget(self.apply_all_cb)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        btn_skip = QPushButton("Skip")
        btn_skip.setToolTip("Don't copy this file")
        btn_skip.clicked.connect(lambda: self._finish(ConflictAction.SKIP))
        
        btn_overwrite = QPushButton("Overwrite")
        btn_overwrite.setToolTip("Replace the existing file")
        btn_overwrite.clicked.connect(lambda: self._finish(ConflictAction.OVERWRITE))
        
        btn_rename = QPushButton("Rename")
        btn_rename.setToolTip("Keep both files with a unique name")
        btn_rename.clicked.connect(lambda: self._finish(ConflictAction.RENAME))
        
        btn_cancel = QPushButton("Cancel All")
        btn_cancel.setToolTip("Abort the entire operation")
        btn_cancel.clicked.connect(lambda: self._finish(ConflictAction.CANCEL))
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_skip)
        btn_layout.addWidget(btn_overwrite)
        btn_layout.addWidget(btn_rename)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)
    
    def _finish(self, action: ConflictAction):
        """Set result and close dialog."""
        self.action = action
        self.apply_to_all = self.apply_all_cb.isChecked()
        self.accept()
