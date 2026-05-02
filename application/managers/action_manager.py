"""
ActionManager — Central Hub for UI Actions and Shortcuts

Defines all QActions dynamically based on the Shortcuts model.
"""

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import QWidget
from typing import Dict, Callable, Optional, Tuple

from application.models.shortcuts import Shortcuts, ShortcutAction
from application.models.icon_mapping import get_ligature


class ActionManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions: Dict[ShortcutAction, QAction] = {}

    # Mapping: Action Name -> (Icon Name, Display Text)
    # We use strings as keys for easier QML integration
    ACTION_METADATA = {
        "COPY": ("edit-copy-symbolic", "Copy"),
        "CUT": ("edit-cut-symbolic", "Cut"),
        "PASTE": ("edit-paste-symbolic", "Paste"),
        "TRASH": ("user-trash-symbolic", "Move to Trash"),
        "RENAME": ("edit-rename-symbolic", "Rename"),
        "DUPLICATE": ("edit-copy-symbolic", "Duplicate"),
        "NEW_FOLDER": ("folder-new-symbolic", "New Folder"),
        "DELETE_PERMANENT": ("edit-delete-symbolic", "Delete Permanently"),
        "UNDO": ("edit-undo-symbolic", "Undo"),
        "REDO": ("edit-redo-symbolic", "Redo"),
        "GO_UP": ("go-up-symbolic", "Go Up"),
        "GO_BACK": ("go-previous-symbolic", "Back"),
        "GO_FORWARD": ("go-next-symbolic", "Forward"),
        "GO_HOME": ("go-home-symbolic", "Home"),
        "REFRESH": ("view-refresh-symbolic", "Refresh"),
        "FIND": ("edit-find-symbolic", "Find"),
        "TOGGLE_HIDDEN": ("view-hidden-symbolic", "Toggle Hidden Files"),
        "ZOOM_IN": ("zoom-in-symbolic", "Zoom In"),
        "ZOOM_OUT": ("zoom-out-symbolic", "Zoom Out"),
        "ZOOM_RESET": ("zoom-original-symbolic", "Reset Zoom"),
        "SELECT_ALL": ("edit-select-all-symbolic", "Select All"),
        "NEW_TAB": ("tab-new-symbolic", "New Tab"),
        "CLOSE_TAB": ("window-close-symbolic", "Close Tab"),
        "EDIT": ("document-edit-symbolic", "Edit"),
    }

    @Slot(str, result=str)
    def get_icon(self, action_name: str) -> str:
        """Returns the icon name for a given action string."""
        return self.ACTION_METADATA.get(action_name, ("", ""))[0]

    @Slot(str, result=str)
    def get_md3_ligature(self, action_name: str) -> str:
        """Returns the MD3 ligature for a given action string."""
        return get_ligature(action_name)

    def setup_actions(
        self,
        window: QWidget,
        shortcuts: Shortcuts,
        file_manager,
        view_manager,
        shell_manager,
        undo_manager,
    ):
        """
        Creates all actions based on the Shortcuts model and registers them.
        """

        # Mapping: Enum -> Slot Function
        # (Icons/Text now come from ACTION_METADATA)
        slots: Dict[ShortcutAction, Optional[Callable]] = {
            ShortcutAction.COPY: file_manager.copy_selection,
            ShortcutAction.CUT: file_manager.cut_selection,
            ShortcutAction.PASTE: file_manager.paste_to_current,
            ShortcutAction.TRASH: file_manager.trash_selection,
            ShortcutAction.RENAME: file_manager.rename_selection,
            ShortcutAction.DUPLICATE: file_manager.duplicate_selection,
            ShortcutAction.NEW_FOLDER: file_manager.create_new_folder,
            ShortcutAction.DELETE_PERMANENT: None,
            ShortcutAction.UNDO: undo_manager.undo,
            ShortcutAction.REDO: undo_manager.redo,
            ShortcutAction.GO_UP: window.go_up,
            ShortcutAction.GO_BACK: shell_manager.go_back,
            ShortcutAction.GO_FORWARD: shell_manager.go_forward,
            ShortcutAction.GO_HOME: shell_manager.go_home,
            ShortcutAction.REFRESH: lambda: (
                shell_manager.current_pane.scanner.scan_directory(
                    shell_manager.current_pane.current_path
                )
                if shell_manager.current_pane
                else None
            ),
            ShortcutAction.FIND: lambda: shell_manager.navigationRequested.emit(
                "FOCUS"
            ),
            ShortcutAction.FOCUS_PATH_BAR: lambda: (
                shell_manager.navigationRequested.emit("FOCUS")
            ),
            ShortcutAction.TOGGLE_HIDDEN: view_manager.toggle_hidden,
            ShortcutAction.ZOOM_IN: view_manager.zoom_in,
            ShortcutAction.ZOOM_OUT: view_manager.zoom_out,
            ShortcutAction.ZOOM_RESET: view_manager.reset_zoom,
            ShortcutAction.SELECT_ALL: view_manager.select_all,
            ShortcutAction.NEW_TAB: lambda: shell_manager.add_tab(),
            ShortcutAction.CLOSE_TAB: lambda: shell_manager.close_current_tab(),
            ShortcutAction.NEXT_TAB: shell_manager.next_tab,
            ShortcutAction.PREV_TAB: shell_manager.prev_tab,
        }

        # Factory Loop
        for action_enum, slot in slots.items():
            metadata = self.ACTION_METADATA.get(action_enum.name)
            if not metadata:
                # Some actions (like NEXT_TAB) might not have defined icons/text yet
                # or don't need them in menus
                icon_name, text = "", action_enum.name.replace("_", " ").title()
            else:
                icon_name, text = metadata

            self._create_action(window, shortcuts, action_enum, text, icon_name, slot)

        # Register global shortcuts to window
        window.addActions(list(self._actions.values()))

    def _create_action(self, window, shortcuts, enum_id, text, icon_name, slot):
        """Helper to create and register an action."""
        action = QAction(text, window)

        if icon_name:
            action.setIcon(QIcon.fromTheme(icon_name))

        # Get key from Model
        key_seq = shortcuts.get(enum_id)
        if key_seq:
            action.setShortcut(QKeySequence(key_seq))

        action.setShortcutContext(Qt.WindowShortcut)

        if slot:
            action.triggered.connect(slot)

        self._actions[enum_id] = action
        return action

    def get_action(self, enum_id: ShortcutAction) -> Optional[QAction]:
        return self._actions.get(enum_id)
