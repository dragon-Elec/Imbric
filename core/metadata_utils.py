"""
[NEW] MetadataUtils — Centralized File Metadata Logic

Acts as the single source of truth for Gio metadata extraction, formatting,
and icon resolution. Prevents duplication across Scanner, Properties, and UI.

Usage:
    from core.metadata_utils import get_file_info, format_size, resolve_mime_icon
    info = get_file_info("/path/to/file")
    print(f"{info.name} ({format_size(info.size)})")
"""

import os
import stat
import gi
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


# =============================================================================
# CONSTANTS & GIO ATTRIBUTES
# =============================================================================

# Standard attribute sets for efficient querying
# Usage: ",".join([GIO_STANDARD_ATTRS, GIO_TIME_ATTRS])

GIO_STANDARD_ATTRS = (
    "standard::name,standard::display-name,standard::type,standard::size,"
    "standard::is-hidden,standard::is-symlink,standard::symlink-target"
)

GIO_MIME_ATTRS = (
    "standard::content-type,standard::fast-content-type"
)

GIO_TIME_ATTRS = (
    "time::modified,time::access,time::created"
)

GIO_ICON_ATTRS = (
    "standard::icon,standard::symbolic-icon"
)

GIO_ACCESS_ATTRS = (
    "unix::mode,unix::uid,unix::gid,owner::user,owner::group"
)

# Combined sets for common use cases
ATTRS_BASIC = f"{GIO_STANDARD_ATTRS},{GIO_MIME_ATTRS}"
ATTRS_FULL = f"{GIO_STANDARD_ATTRS},{GIO_MIME_ATTRS},{GIO_TIME_ATTRS},{GIO_ACCESS_ATTRS},{GIO_ICON_ATTRS}"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FileInfo:
    """
    Unified file metadata structure.
    Superset of what FileScanner and FileProperties use.
    """
    path: str
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
    
    # Timestamps (Unix)
    modified_ts: int = 0
    accessed_ts: int = 0
    created_ts: int = 0
    
    # Permissions
    mode: int = 0
    permissions_str: str = ""  # "-rw-r--r--"
    owner: str = ""
    group: str = ""


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string (B, KB, MB, GB...).
    """
    if size_bytes < 0:
        return "0 B"
        
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def to_unix_timestamp(dt: GLib.DateTime | None) -> int:
    """
    Safe convert GLib.DateTime to Unix timestamp (int).
    Returns 0 if None.
    """
    if dt is None:
        return 0
    try:
        return int(dt.to_unix())
    except (GLib.Error, ValueError, OverflowError):
        return 0


def unix_mode_to_str(mode: int) -> str:
    """
    Convert raw unix mode (int) to string format (e.g. '-rw-r--r--').
    """
    try:
        return stat.filemode(mode)
    except Exception:
        return "??????????"


# =============================================================================
# GIO LOGIC
# =============================================================================

def resolve_mime_icon(gfile: Gio.File, cancellable: Gio.Cancellable = None) -> str:
    """
    Resolve the desktop theme icon name for a file using Gio.
    
    Args:
        gfile: Gio.File object
        cancellable: Optional cancellation token
        
    Returns:
        String icon name (e.g. "text-plain", "folder")
    """
    try:
        # We only need the icon attribute
        info = gfile.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, cancellable)
        gicon = info.get_icon()
        
        if gicon:
            # GIcon (ThemedIcon) usually holds a list of names in order of preference
            if hasattr(gicon, 'get_names'):
                names = gicon.get_names()
                if names:
                    # Return the first (most specific) one
                    # The UI layer (QIcon.fromTheme) will handle fallbacks if the specific one is missing
                    return names[0]
            
            # Fallback for GIcons that aren't ThemedIcons (rare for files, but possible)
            # We could try to_string() but it might be a serialization
            pass
            
    except GLib.Error:
        pass
        
    # Ultimate fallback
    return "application-x-generic"


def get_file_info(path: str, attributes: str = ATTRS_FULL) -> Optional[FileInfo]:
    """
    Synchronously fetch and populate FileInfo for a path.
    
    Args:
        path: Absolute path
        attributes: Gio attribute string (default: all)
        
    Returns:
        FileInfo object or None if file doesn't exist/error.
    """
    gfile = Gio.File.new_for_path(path)
    
    try:
        # Resolve symlinks for the main query? 
        # Usually we want info about the link itself (NOFOLLOW), 
        # but for properties we might want target info.
        # Standard Imbric behavior: Show info for the file itself (Link is a Link).
        
        info = gfile.query_info(
            attributes,
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            None
        )
        
        # 1. Basic Info
        name = info.get_name()
        display_name = info.get_display_name()
        size = info.get_size()
        
        file_type = info.get_file_type()
        is_dir = (file_type == Gio.FileType.DIRECTORY)
        is_symlink = info.get_is_symlink()
        is_hidden = info.get_is_hidden()
        
        symlink_target = info.get_symlink_target() if is_symlink else ""
        
        # 2. MIME & Icon
        mime_type = info.get_content_type() or "application/octet-stream"
        
        # Extract Icon Name
        icon_name = "application-x-generic"
        gicon = info.get_icon()
        if gicon and hasattr(gicon, 'get_names'):
            names = gicon.get_names()
            if names:
                icon_name = names[0]
        
        # 3. Timestamps
        m_time = to_unix_timestamp(info.get_modification_date_time())
        a_time = to_unix_timestamp(info.get_access_date_time())
        c_time = to_unix_timestamp(info.get_creation_date_time())
        
        # 4. Permissions
        mode = info.get_attribute_uint32("unix::mode")
        perm_str = unix_mode_to_str(mode)
        
        owner = info.get_attribute_string("owner::user") or str(info.get_attribute_uint32("unix::uid"))
        group = info.get_attribute_string("owner::group") or str(info.get_attribute_uint32("unix::gid"))
        
        return FileInfo(
            path=path,
            name=name,
            display_name=display_name,
            size=size,
            size_human=format_size(size),
            is_dir=is_dir,
            is_symlink=is_symlink,
            symlink_target=symlink_target,
            is_hidden=is_hidden,
            mime_type=mime_type,
            icon_name=icon_name,
            modified_ts=m_time,
            accessed_ts=a_time,
            created_ts=c_time,
            mode=mode,
            permissions_str=perm_str,
            owner=owner,
            group=group
        )
        
    except GLib.Error as e:
        # Expected for non-existent files or permission errors during scan
        # print(f"[MetadataUtils] Error querying {path}: {e}")
        return None
