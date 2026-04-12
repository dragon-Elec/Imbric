from PySide6.QtCore import QObject, Signal, Property, Slot

from ui.bridges.search_bridge import SearchBridge
from ui.bridges.rename_bridge import RenameBridge
from ui.bridges.drag_bridge import DragBridge
from ui.bridges.navigation_bridge import NavigationBridge


class AppBridge(QObject):
    pathChanged = Signal(str)
    requestContextMenu = Signal(list)
    renameRequested = Signal(str)
    cutPathsChanged = Signal()

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        self.search = SearchBridge(main_window)
        self.rename = RenameBridge(main_window)
        self.drag = DragBridge(main_window)
        self.navigation = NavigationBridge(main_window)

        self.navigation.cutPathsChanged.connect(self.cutPathsChanged)

        self._pending_select_paths = []
        self._pending_rename_path = None

    def queueSelectionAfterRefresh(self, paths):
        self._pending_select_paths = paths

    def selectPendingPaths(self):
        paths = self._pending_select_paths
        self._pending_select_paths = []
        return paths

    @Property(list, notify=cutPathsChanged)
    def cutPaths(self):
        return self.navigation.cutPaths

    @Slot(list, str, str)
    def handleDrop(self, urls, dest_dir="", mode="auto"):
        self.drag.handleDrop(urls, dest_dir, mode)

    @Slot(list)
    def showContextMenu(self, paths):
        self.requestContextMenu.emit(paths)

    @Slot()
    def showBackgroundContextMenu(self):
        self.requestContextMenu.emit([])

    @Slot(str, str)
    def renameFile(self, old_path, new_name):
        self.rename.renameFile(old_path, new_name)

    @Slot(int)
    def zoom(self, delta):
        self.navigation.zoom(delta)

    @Slot(str)
    def openPath(self, path):
        self.navigation.openPath(path)
