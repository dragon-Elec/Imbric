"""
Pure data model for file metadata.
No external dependencies (no GIO, no Qt).
"""

from dataclasses import dataclass


@dataclass(kw_only=True)
class FileInfo:
    """Unified file metadata structure."""

    path: str
    uri: str
    name: str
    display_name: str
    size: int = 0
    size_human: str = ""

    is_dir: bool = False
    is_symlink: bool = False
    symlink_target: str = ""
    is_hidden: bool = False

    mime_type: str = "application/octet-stream"
    icon_name: str = "application-x-generic"

    modified_ts: int = 0
    accessed_ts: int = 0
    created_ts: int = 0

    mode: int = 0
    permissions_str: str = ""
    owner: str = ""
    group: str = ""
    can_write: bool = True

    target_uri: str = ""
    trash_orig_path: str = ""
    trash_deletion_date: str = ""
