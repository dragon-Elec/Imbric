"""
ClipboardManager.py

Wraps Qt's QClipboard for file operations (Cut/Copy/Paste).
Uses standard MIME types for interoperability with other file managers.
"""

from PySide6.QtCore import QObject, Signal, Slot, QMimeData, QUrl
from PySide6.QtGui import QClipboard, QGuiApplication
from typing import List
import os


class ClipboardManager(QObject):
    """
    Manages clipboard operations for file paths.
    Supports both "copy" (duplicate) and "cut" (move) modes.
    Compatible with Nautilus, Dolphin, Nemo, etc.
    """
    
    # Signals
    clipboardChanged = Signal()
    
    # MIME type used by file managers for cut/copy distinction
    GNOME_COPIED_FILES = "x-special/gnome-copied-files"
    URI_LIST = "text/uri-list"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cut = False  # True = Cut (move), False = Copy
        self._clipboard = QGuiApplication.clipboard()
        
        # Connect to system clipboard changes
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
    
    # -------------------------------------------------------------------------
    # COPY TO CLIPBOARD
    # -------------------------------------------------------------------------
    @Slot(list)
    def copy(self, paths: list):
        """
        Copies file paths to clipboard.
        """
        self._set_clipboard(paths, is_cut=False)
    
    # -------------------------------------------------------------------------
    # CUT TO CLIPBOARD
    # -------------------------------------------------------------------------
    @Slot(list)
    def cut(self, paths: list):
        """
        Cuts file paths to clipboard (marks for move).
        """
        self._set_clipboard(paths, is_cut=True)
    
    # -------------------------------------------------------------------------
    # GET CLIPBOARD CONTENTS
    # -------------------------------------------------------------------------
    @Slot(result=list)
    def getFiles(self) -> List[str]:
        """
        Returns list of file paths currently in clipboard.
        """
        mime_data = self._clipboard.mimeData()
        if not mime_data:
            return []
        
        # Try to get URIs
        if mime_data.hasUrls():
            return [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]
        
        return []
    
    @Slot(result=bool)
    def isCut(self) -> bool:
        """
        Returns True if clipboard contains "cut" files (for move).
        Returns False if clipboard contains "copy" files (for duplicate).
        """
        mime_data = self._clipboard.mimeData()
        if not mime_data:
            return False
        
        # Check GNOME-style marker
        if mime_data.hasFormat(self.GNOME_COPIED_FILES):
            data = bytes(mime_data.data(self.GNOME_COPIED_FILES)).decode('utf-8')
            return data.startswith("cut")
        
        return self._is_cut
    
    @Slot(result=bool)
    def hasFiles(self) -> bool:
        """
        Returns True if clipboard contains file paths.
        """
        mime_data = self._clipboard.mimeData()
        return mime_data is not None and mime_data.hasUrls()
    
    # -------------------------------------------------------------------------
    # CLEAR CLIPBOARD
    # -------------------------------------------------------------------------
    @Slot()
    def clear(self):
        """
        Clears the clipboard.
        """
        self._clipboard.clear()
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    def _set_clipboard(self, paths: list, is_cut: bool):
        """
        Sets clipboard content with file paths.
        Uses GNOME-compatible MIME format for interoperability.
        """
        self._is_cut = is_cut
        
        mime_data = QMimeData()
        
        # 1. Set URLs (standard)
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)
        
        # 2. Set GNOME-style format for cut/copy distinction
        # Format: "cut\nfile://path1\nfile://path2\n..." or "copy\n..."
        action = "cut" if is_cut else "copy"
        uri_list = "\n".join(["file://" + p for p in paths])
        gnome_data = f"{action}\n{uri_list}"
        mime_data.setData(self.GNOME_COPIED_FILES, gnome_data.encode('utf-8'))
        
        # 3. Set plain URI list as well
        mime_data.setData(self.URI_LIST, uri_list.encode('utf-8'))
        
        self._clipboard.setMimeData(mime_data)
    
    def _on_clipboard_changed(self):
        """
        Called when system clipboard content changes.
        """
        self.clipboardChanged.emit()
