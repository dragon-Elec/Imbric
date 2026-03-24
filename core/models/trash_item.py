"""
TrashItem dataclass - represents an item in the trash.
No external dependencies.
"""

from dataclasses import dataclass


@dataclass
class TrashItem:
    """Represents an item in the trash."""

    trash_name: str  # Internal name in trash (e.g., "file.2.txt")
    display_name: str  # Original filename (e.g., "file.txt")
    original_path: str  # Where it came from (e.g., "/home/user/file.txt")
    deletion_date: str  # ISO format date string
    trash_uri: str  # Full URI (e.g., "trash:///file.2.txt")
    size: int = 0
    is_dir: bool = False
