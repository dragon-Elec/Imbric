"""
ConflictDialog — File Conflict Resolution Dialog

A reusable dialog for handling file name conflicts during copy/move operations.
Provides Skip/Overwrite/Rename/Cancel options with "Apply to all" support.

Design Notes:
- Each paste/drop operation creates one ConflictResolver instance
- The resolver tracks "apply to all" state for that batch
- This design works with future multi-pane/tab/window: each operation is independent
"""

from enum import Enum, auto
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import os


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
        filename = os.path.basename(dest_path)
        dest_dir = os.path.dirname(dest_path)
        
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


class ConflictResolver:
    """
    Stateful helper for resolving file conflicts during a batch operation.
    """
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self._apply_all_action = None  # Cached action when "apply to all" is set
    
    def resolve(self, src_path: str, dest_path: str) -> tuple[ConflictAction, str]:
        """
        Resolve a potential file conflict (Standard Mode: Copy/Paste).
        Naming Style: "file (Copy).txt"
        """
        return self._resolve_internal(src_path, dest_path, naming_template="{base} (Copy){ext}")

    def resolve_rename(self, old_path: str, new_path: str) -> tuple[ConflictAction, str]:
        """
        Resolve a potential file conflict (Rename Mode).
        Naming Style: "file (2).txt"
        """
        # Note: 'Skip' is synonymous with 'Cancel' for a single rename op,
        # but we treat it as CANCEL for safety.
        # We pass naming_template for counter-based naming
        return self._resolve_internal(old_path, new_path, naming_template="{base} ({counter}){ext}", start_counter=2)

    def _resolve_internal(self, src, dest, naming_template="{base} (Copy){ext}", start_counter=1) -> tuple[ConflictAction, str]:
        if not os.path.exists(dest):
            return (ConflictAction.OVERWRITE, dest)
        
        filename = os.path.basename(dest)
        
        # Check cache
        if self._apply_all_action is not None:
            return self._process_action(self._apply_all_action, dest, naming_template, start_counter)
        
        # Show Dialog
        dialog = ConflictDialog(self.parent, src, dest)
        dialog.exec()
        action = dialog.action
        
        if dialog.apply_to_all:
            self._apply_all_action = action
            
        return self._process_action(action, dest, naming_template, start_counter)
    
    def _process_action(self, action, dest_path, template, start_counter):
        if action == ConflictAction.SKIP:
            return (ConflictAction.SKIP, "")
        elif action == ConflictAction.CANCEL:
            return (ConflictAction.CANCEL, "")
        elif action == ConflictAction.OVERWRITE:
            return (ConflictAction.OVERWRITE, dest_path)
        elif action == ConflictAction.RENAME:
            unique = self._generate_unique_name(dest_path, template, start_counter)
            return (ConflictAction.RENAME, unique)
        
        return (ConflictAction.CANCEL, "")
    
    def _generate_unique_name(self, dest_path: str, template: str, start_counter: int) -> str:
        """Generate a unique filename using a template."""
        folder = os.path.dirname(dest_path)
        filename = os.path.basename(dest_path)
        
        # Handle double extensions (e.g. .tar.gz)
        # os.path.splitext only splits the last one
        if filename.endswith(".tar.gz"):
            base = filename[:-7]
            ext = ".tar.gz"
        else:
            base, ext = os.path.splitext(filename)
        
        # First try: might be "file (Copy).txt" or "file (2).txt" 
        # For copy: default is just " (Copy)" first time, then " (Copy 2)"
        # For rename: just "(2)"
        
        # Special logic for "(Copy)" vs counters
        # If template has {counter}, we loops.
        # If template is the default (Copy), we do (Copy) then (Copy 2)
        
        if "(Copy)" in template:
             # Standard copy logic (Legacy behavior preserved)
            current = f"{base} (Copy){ext}"
            check_path = os.path.join(folder, current)
            if not os.path.exists(check_path):
                return check_path
                
            counter = 2
            while True:
                current = f"{base} (Copy {counter}){ext}"
                check_path = os.path.join(folder, current)
                if not os.path.exists(check_path):
                    return check_path
                counter += 1
        else:
            # Counter logic (Rename style: file (2), file (3))
            counter = start_counter
            while True:
                current = template.format(base=base, counter=counter, ext=ext)
                check_path = os.path.join(folder, current)
                if not os.path.exists(check_path):
                    return check_path
                counter += 1
