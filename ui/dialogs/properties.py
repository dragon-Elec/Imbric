"""
Properties Dialog & Logic

Self-contained module for File Properties.
Consolidates:
- FilePropertiesModel (Logic)
- PropertiesDialog (UI - to be implemented/refactored if needed, currently just logic stub)
"""

from PySide6.QtCore import QObject, Signal, Slot
from datetime import datetime
import os
from core.metadata_utils import get_file_info, format_size

class PropertiesLogic(QObject):
    """
    Reads detailed file properties.
    Replaces FilePropertiesModel.
    """
    propertiesReady = Signal(list)

    @Slot(str, result=dict)
    def get_properties(self, path: str) -> dict:
        info = get_file_info(path)
        if not info: return {}
        
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
            "created": datetime.fromtimestamp(info.created_ts) if info.created_ts else None,
            "modified": datetime.fromtimestamp(info.modified_ts) if info.modified_ts else None,
            "accessed": datetime.fromtimestamp(info.accessed_ts) if info.accessed_ts else None
        }

    @Slot(list)
    def get_properties_async(self, paths: list):
        results = [self.get_properties(p) for p in paths if p]
        self.propertiesReady.emit(results)
        
    @Slot(int, result=str)
    def format_size(self, size_bytes: int) -> str:
        return format_size(size_bytes)
