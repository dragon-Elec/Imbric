"""
GIO Backend - All GIO-based implementations.
"""

from core.backends.gio.helpers import _make_gfile, _gfile_path, ensure_uri
from core.backends.gio.metadata import get_file_info
from core.backends.gio.io_ops import (
    TransferRunnable,
    RenameRunnable,
    CreateFolderRunnable,
    CreateFileRunnable,
    CreateSymlinkRunnable,
)
from core.backends.gio.trash_ops import (
    SendToTrashRunnable,
    RestoreFromTrashRunnable,
    ListTrashRunnable,
    EmptyTrashRunnable,
)
from core.backends.gio.scanner import FileScanner
from core.backends.gio.monitor import FileMonitor
from core.backends.gio.volumes import VolumesBridge
from core.backends.gio.desktop import (
    QuickAccessBridge,
    BookmarksBridge,
    get_breadcrumb_segments,
    create_desktop_mime_data,
    open_with_default_app,
)
from core.backends.gio.metadata_workers import (
    ItemCountWorker,
    DimensionWorker,
    PropertiesWorker,
)

__all__ = [
    "_make_gfile",
    "_gfile_path",
    "ensure_uri",
    "get_file_info",
    "TransferRunnable",
    "RenameRunnable",
    "CreateFolderRunnable",
    "CreateFileRunnable",
    "CreateSymlinkRunnable",
    "SendToTrashRunnable",
    "RestoreFromTrashRunnable",
    "ListTrashRunnable",
    "EmptyTrashRunnable",
    "FileScanner",
    "FileMonitor",
    "VolumesBridge",
    "QuickAccessBridge",
    "BookmarksBridge",
    "get_breadcrumb_segments",
    "create_desktop_mime_data",
    "open_with_default_app",
    "ItemCountWorker",
    "DimensionWorker",
    "PropertiesWorker",
]
