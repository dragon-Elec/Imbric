"""
Pure formatting utilities - no GIO, no Qt.
"""

import stat


def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string (B, KB, MB, GB...).
    """
    if size_bytes < 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def unix_mode_to_str(mode: int) -> str:
    """
    Convert raw unix mode (int) to string format (e.g. '-rw-r--r--').
    """
    try:
        return stat.filemode(mode)
    except Exception:
        return "??????????"
