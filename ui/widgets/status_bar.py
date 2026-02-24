"""
StatusBar - Shows item counts and selection info.

Like Nemo/Nautilus bottom bar:
- Idle: "X items (Y folders, Z files)"
- Selection: "X items selected"
"""

from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtCore import Slot


class StatusBar(QStatusBar):
    """
    Status bar showing directory item counts and selection info.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Main status label (left side)
        self._status_label = QLabel("0 items")
        self.addWidget(self._status_label, 1)
        
        # Item counts (cached for selection updates)
        self._total_items = 0
        self._folder_count = 0
        self._file_count = 0
    
    @Slot(str, list)
    def updateItemCount(self, session_id: str, files: list):
        """
        Called when files are loaded in a directory.
        files: list of dicts with 'path', 'isDir', etc.
        session_id: ignored here (StatusBar doesn't filter by session).
        
        Note: Scanner emits files in batches, so we ACCUMULATE counts.
        Call resetCounts() before a new directory scan.
        """
        # Accumulate counts
        batch_folders = sum(1 for f in files if f.get('isDir', False))
        batch_files = len(files) - batch_folders
        
        self._total_items += len(files)
        self._folder_count += batch_folders
        self._file_count += batch_files
        
        self._show_idle_status()
    
    @Slot()
    def resetCounts(self):
        """Reset counts before a new directory scan."""
        self._total_items = 0
        self._folder_count = 0
        self._file_count = 0
    
    @Slot(str, str, object)
    def updateAttribute(self, path: str, attr_name: str, value: object):
        """Called for async updates (like child counts)."""
        # For now, we don't update the bottom bar text for every attribute,
        # but we could show a 'Calculating sizes...' message.
        pass

    @Slot(str)
    def setMessage(self, message: str):
        """Show a temporary message in the status bar."""
        self._status_label.setText(message)

    @Slot(list)
    def updateSelection(self, selected_paths: list):
        """
        Called when selection changes.
        Shows selection count or reverts to idle status.
        """
        count = len(selected_paths)
        
        if count > 0:
            self._status_label.setText(f"{count} item{'s' if count != 1 else ''} selected")
        else:
            self._show_idle_status()
    
    def _show_idle_status(self):
        """Shows the default idle status with item counts."""
        if self._total_items == 0:
            self._status_label.setText("Empty folder")
        elif self._folder_count > 0 and self._file_count > 0:
            self._status_label.setText(
                f"{self._total_items} items ({self._folder_count} folders, {self._file_count} files)"
            )
        elif self._folder_count > 0:
            self._status_label.setText(
                f"{self._folder_count} folder{'s' if self._folder_count != 1 else ''}"
            )
        else:
            self._status_label.setText(
                f"{self._file_count} file{'s' if self._file_count != 1 else ''}"
            )
