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


import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from PySide6.QtCore import QObject, Signal, Slot
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime
import os
import stat


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
            Dict with all FileInfo fields (converted to dict for QML/Python compatibility)
        """
        gfile = Gio.File.new_for_path(path)
        try:
            # Query all needed attributes
            info = gfile.query_info(
                "standard::*,unix::*,time::*,owner::*",
                Gio.FileQueryInfoFlags.NONE,
                None
            )
            
            # Extract basic info
            name = info.get_name()
            size = info.get_size()
            file_type = info.get_file_type()
            is_dir = (file_type == Gio.FileType.DIRECTORY)
            is_symlink = (file_type == Gio.FileType.SYMBOLIC_LINK)
            
            # Symlink target
            symlink_target = info.get_symlink_target()
            
            # Mime Type
            mime_type = info.get_content_type()
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # Permissions
            mode = info.get_attribute_uint32("unix::mode")
            permissions = stat.filemode(mode)
            
            # Ownership
            owner = info.get_attribute_string("owner::user") or str(info.get_attribute_uint32("unix::uid"))
            group = info.get_attribute_string("owner::group") or str(info.get_attribute_uint32("unix::gid"))
            
            # Timestamps
            created_ts = info.get_attribute_uint64("time::created")
            modified_ts = info.get_attribute_uint64("time::modified")
            accessed_ts = info.get_attribute_uint64("time::access")
            
            created = datetime.fromtimestamp(created_ts) if created_ts else None
            modified = datetime.fromtimestamp(modified_ts) if modified_ts else datetime.now()
            accessed = datetime.fromtimestamp(accessed_ts) if accessed_ts else datetime.now()
            
            file_info = FileInfo(
                path=path,
                name=name,
                size=size,
                size_human=self.format_size(size),
                is_dir=is_dir,
                is_symlink=is_symlink,
                symlink_target=symlink_target,
                mime_type=mime_type,
                permissions=permissions,
                owner=owner,
                group=group,
                created=created,
                modified=modified,
                accessed=accessed
            )
            
            # Return as dict for generic use
            return file_info.__dict__
            
        except GLib.Error as e:
            print(f"Error getting properties for {path}: {e}")
            return {}
    
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
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    @Slot(str, result=str)
    def get_mime_type(self, path: str) -> str:
        """Get MIME type for a file."""
        try:
            gfile = Gio.File.new_for_path(path)
            info = gfile.query_info(
                "standard::content-type", 
                Gio.FileQueryInfoFlags.NONE, 
                None
            )
            return info.get_content_type()
        except GLib.Error:
            return "application/octet-stream"
    
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
