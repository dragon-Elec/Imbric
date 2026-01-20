"""
[STUB] FileProperties — File Metadata Reader

Reads file properties (size, permissions, dates, owner, mime-type).
Used for Properties dialog and detailed view columns.

Usage:
    props = FileProperties()
    info = props.get_properties("/path/to/file")
    # info = {"size": 1024, "modified": datetime, "permissions": "-rw-r--r--", ...}
    
Integration:
    - Properties dialog shows this info
    - Details/List view uses subset for columns
    - Scanner could use this for sorting metadata
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FileInfo:
    """Structured file metadata."""
    path: str
    name: str
    size: int                    # Bytes (0 for directories)
    size_human: str              # "1.2 MB"
    is_dir: bool
    is_symlink: bool
    symlink_target: Optional[str]
    mime_type: str               # "image/jpeg"
    permissions: str             # "-rw-r--r--" or "drwxr-xr-x"
    owner: str                   # Username
    group: str                   # Group name
    created: Optional[datetime]  # May not be available on all filesystems
    modified: datetime
    accessed: datetime


class FileProperties(QObject):
    """
    Reads detailed file properties using Gio.
    Synchronous (fast for single file), async batch version for lists.
    """
    
    # Signal for async batch queries
    propertiesReady = Signal(list)  # List of FileInfo dicts
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(str, result=dict)
    def get_properties(self, path: str) -> dict:
        """
        Get properties for a single file.
        
        Args:
            path: Absolute file path
            
        Returns:
            Dict with all FileInfo fields
        """
        raise NotImplementedError("TODO: Implement - Use Gio.File.query_info()")
    
    @Slot(list)
    def get_properties_async(self, paths: list):
        """
        Get properties for multiple files (async).
        Emits propertiesReady when done.
        """
        raise NotImplementedError("TODO: Implement - Batch query with Gio async")
    
    @Slot(int, result=str)
    def format_size(self, size_bytes: int) -> str:
        """
        Format byte size as human-readable string.
        
        Examples:
            1024 → "1 KB"
            1048576 → "1 MB"
            1073741824 → "1 GB"
        """
        raise NotImplementedError("TODO: Implement - Human readable size formatting")
    
    @Slot(str, result=str)
    def get_mime_type(self, path: str) -> str:
        """Get MIME type for a file."""
        raise NotImplementedError("TODO: Implement - Gio.content_type_guess or query_info")
    
    @Slot(str, result=bool)
    def is_symlink(self, path: str) -> bool:
        """Check if path is a symbolic link."""
        raise NotImplementedError("TODO: Implement - os.path.islink or Gio")
    
    @Slot(str, result=str)
    def get_symlink_target(self, path: str) -> Optional[str]:
        """Get the target of a symbolic link."""
        raise NotImplementedError("TODO: Implement - os.readlink or Gio")
