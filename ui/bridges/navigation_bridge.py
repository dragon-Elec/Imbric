from PySide6.QtCore import QObject, Signal, Property, Slot


class NavigationBridge(QObject):
    cutPathsChanged = Signal()

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        self.mw.clipboard.clipboardChanged.connect(self._on_clipboard_changed)

    def _on_clipboard_changed(self):
        self.cutPathsChanged.emit()

    @Property(list, notify=cutPathsChanged)
    def cutPaths(self):
        return self.mw.file_manager.get_cut_paths()

    @Slot(str)
    def openPath(self, path: str):
        self.mw.shell_manager.navigate_to(path)

    @Slot()
    def paste(self):
        self.mw.file_manager.paste_to_current()

    @Slot(int)
    def zoom(self, delta):
        if delta > 0:
            self.mw.view_manager.zoom_in()
        else:
            self.mw.view_manager.zoom_out()
