"""
DeviceProvider ABC - Contract for Volume/MTP monitoring.
"""

from PySide6.QtCore import QObject, Signal, Slot, Property


class DeviceProvider(QObject):
    """Contract for Volume/MTP monitoring."""

    volumesChanged = Signal()
    mountSuccess = Signal(str)
    mountError = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @Property(str, constant=True)
    def title(self):
        return "Devices"

    @Property(str, constant=True)
    def icon(self):
        return "hard_drive"

    @Slot(result=list)
    def get_volumes(self) -> list:
        """Return a list of dictionary items representing volumes/mounts."""
        return []

    @Slot(str)
    def mount_volume(self, identifier: str) -> None:
        """Mount a volume by its identifier."""
        pass

    @Slot(str)
    def unmount_volume(self, identifier: str) -> None:
        """Unmount a volume by its identifier."""
        pass
