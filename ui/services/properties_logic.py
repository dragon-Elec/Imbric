"""
Properties Dialog & Logic

Self-contained module for File Properties.
Consolidates:
- FilePropertiesModel (Logic)
- PropertiesDialog (UI - to be implemented/refactored if needed, currently just logic stub)
"""

from PySide6.QtCore import QObject, Signal, Slot
from core.gio_bridge.properties_worker import PropertiesWorker
from core.metadata_utils import format_size


class PropertiesLogic(QObject):
    """
    Reads detailed file properties asynchronously.
    
    Uses PropertiesWorker (QThreadPool) to avoid blocking the UI
    on network drives (FTP, SMB, MTP).
    """
    propertiesReady = Signal(str, dict)  # (path, properties_dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = PropertiesWorker(self)
        self._worker.propertiesReady.connect(self._on_result)

    def _on_result(self, path: str, props: dict):
        """Forward the worker result to the UI."""
        self.propertiesReady.emit(path, props)

    @Slot(str)
    def request_properties(self, path: str):
        """Request properties for a single file (async, non-blocking)."""
        self._worker.enqueue(path)

    @Slot(list)
    def request_properties_batch(self, paths: list):
        """Request properties for multiple files (async, non-blocking)."""
        self._worker.enqueue_batch(paths)

    @Slot(int, result=str)
    def format_size(self, size_bytes: int) -> str:
        return format_size(size_bytes)
