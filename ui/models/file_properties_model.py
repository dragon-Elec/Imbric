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
from typing import Optional, List
from datetime import datetime
import os

# Import core metadata utilities
from core.metadata_utils import get_file_info, format_size


class FilePropertiesModel(QObject):
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
            Dict with FileInfo fields (converted to dict for QML/Python compatibility).
            NOTE: Timestamps are datetime objects.
        """
        info = get_file_info(path)
        
        if not info:
            return {}
            
        # Convert timestamps back to datetime for API compatibility
        created = datetime.fromtimestamp(info.created_ts) if info.created_ts else None
        modified = datetime.fromtimestamp(info.modified_ts) if info.modified_ts else datetime.now()
        accessed = datetime.fromtimestamp(info.accessed_ts) if info.accessed_ts else datetime.now()
        
        return {
            "path": info.path,
            "name": info.name,
            "size": info.size,
            "size_human": info.size_human,
            "is_dir": info.is_dir,
            "is_symlink": info.is_symlink,
            "symlink_target": info.symlink_target,
            "mime_type": info.mime_type,
            "permissions": info.permissions_str,
            "owner": info.owner,
            "group": info.group,
            "created": created,
            "modified": modified,
            "accessed": accessed
        }
    
    @Slot(list)
    def get_properties_async(self, paths: list):
        """
        Get properties for multiple files (async).
        Emits propertiesReady when done.
        """
        # TODO: Implement true async version if needed. 
        # For now, batch-process synchronously but it's fast enough for small selection.
        results = []
        for path in paths:
            props = self.get_properties(path)
            if props:
                results.append(props)
        self.propertiesReady.emit(results)
    
    @Slot(int, result=str)
    def format_size(self, size_bytes: int) -> str:
        """
        Format byte size as human-readable string.
        Delegates to metadata_utils.
        """
        return format_size(size_bytes)
    
    @Slot(str, result=str)
    def get_mime_type(self, path: str) -> str:
        """Get MIME type for a file."""
        # We could use get_file_info here, but might be overkill to query all attributes.
        # However, for consistency and simplicity in this refactor, let's just stick to 
        # the pattern or keep light wrapper. 
        # To strictly use utils, we can use a targeted query if utils supported it, 
        # but utils.get_file_info gets everything by default.
        # Let's just create a quick targeted query here to avoid 'stat' overhead if we implemented it manually.
        # actually, let's blindly rely on utils for now as per "refactor to use utils".
        # Optimization: We could add an 'attributes' arg to get_file_info later.
        
        info = get_file_info(path)
        return info.mime_type if info else "application/octet-stream"
    
    @Slot(str, result=bool)
    def is_symlink(self, path: str) -> bool:
        """Check if path is a symbolic link."""
        return os.path.islink(path)
    
    @Slot(str, result=str)
    def get_symlink_target(self, path: str) -> str:
        """Get the target of a symbolic link."""
        try:
            return os.readlink(path)
        except OSError:
            return ""
