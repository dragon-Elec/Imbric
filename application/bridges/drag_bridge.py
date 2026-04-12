from PySide6.QtCore import QObject, Slot
from application.components.drag_helper import start_drag_session


class DragBridge(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

    @Slot(list)
    def startDrag(self, paths):
        start_drag_session(self.mw, paths)

    @Slot(list, str, str)
    def handleDrop(self, urls, dest_dir: str = "", mode: str = "auto"):
        self.mw.file_manager.handle_drop(urls, dest_dir, mode)
