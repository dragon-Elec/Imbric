from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtCore import Signal, Slot, QUrl, Qt
from PySide6.QtQml import QQmlContext
from pathlib import Path

# Import Bridges
from core.gio_bridge.quick_access import QuickAccessBridge
from core.gio_bridge.volumes import VolumesBridge

class Sidebar(QQuickWidget):
    """
    QML-based Sidebar hosted in a QQuickWidget.
    Replaces the old QTreeView.
    """
    
    navigationRequested = Signal(str)
    mountRequested = Signal(str)
    unmountRequested = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarWidget")
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        
        # Initialize Bridges
        self.quick_access = QuickAccessBridge(self)
        self.volumes = VolumesBridge(self)
        
        # Setup QML
        qml_path = Path(__file__).parent.parent / "qml" / "components" / "Sidebar.qml"
        self.setSource(QUrl.fromLocalFile(str(qml_path.resolve())))
        
        # Check for errors
        if self.status() == QQuickWidget.Status.Error:
            for error in self.errors():
                print(f"Sidebar QML Error: {error.toString()}")
        
        # Connect Signals from Bridges to update QML properties
        self.quick_access.itemsChanged.connect(self._refresh_quick_access)
        self.volumes.volumesChanged.connect(self._refresh_volumes)
        
        # Connect Navigation from QML to Python
        if self.rootObject():
            self.rootObject().navigationRequested.connect(self.navigationRequested.emit)
            self.rootObject().mountRequested.connect(self.volumes.mount_volume)
            self.rootObject().unmountRequested.connect(self.volumes.unmount_volume)
            
        # Initial Load
        self._refresh_quick_access()
        self._refresh_volumes()
            
    def _refresh_quick_access(self):
        """Push updated list to QML."""
        if self.rootObject():
            items = self.quick_access.get_items()
            self.rootObject().setProperty("quickAccessModel", items)

    def _refresh_volumes(self):
        """Push updated list to QML."""
        if self.rootObject():
            items = self.volumes.get_volumes()
            self.rootObject().setProperty("volumesModel", items)

    def sync_to_path(self, path: str):
        """Call QML function to highlight the correct item."""
        if self.rootObject():
            # Invoke the QML function directly
            # Note: arguments must be passed carefully
            self.rootObject().syncToPath(path)
