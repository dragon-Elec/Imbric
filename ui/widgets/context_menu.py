from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QCursor, QIcon
from ui.models.shortcuts import ShortcutAction
from core.backends.gio.desktop import open_with_default_app as _open_file


class FileContextMenu(QMenu):
    """Native QMenu for file and folder operations."""

    def __init__(self, parent, paths):
        super().__init__(parent)
        self.mw = parent
        self.paths = paths
        self._build_menu()

    def _build_menu(self):
        am, fm = self.mw.action_manager, self.mw.file_manager
        is_single = len(self.paths) == 1

        if is_single:
            act_open = self.addAction(QIcon.fromTheme("document-open"), "Open")
            act_open.triggered.connect(lambda: _open_file(self.paths[0]))
            self.addSeparator()

        self.addAction(am.get_action(ShortcutAction.COPY))
        self.addAction(am.get_action(ShortcutAction.CUT))

        act_paste = am.get_action(ShortcutAction.PASTE)
        act_paste.setEnabled(fm.get_clipboard_files() != [])
        self.addAction(act_paste)

        self.addSeparator()
        if is_single:
            self.addAction(am.get_action(ShortcutAction.RENAME))

        self.addSeparator()
        self.addAction(am.get_action(ShortcutAction.TRASH))


class BackgroundContextMenu(QMenu):
    """Native QMenu for empty space interactions."""

    def __init__(self, parent):
        super().__init__(parent)
        self.mw = parent
        self._build_menu()

    def _build_menu(self):
        am, fm = self.mw.action_manager, self.mw.file_manager

        act_paste = am.get_action(ShortcutAction.PASTE)
        act_paste.setEnabled(fm.get_clipboard_files() != [])
        self.addAction(act_paste)

        self.addSeparator()
        self.addAction(am.get_action(ShortcutAction.NEW_FOLDER))
