"""
ActionManager — Central Hub for UI Actions and Shortcuts

Defines all QActions dynamically based on the Shortcuts model.
"""

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import QWidget
from typing import Dict, Callable, Optional, Tuple

from ui.models.shortcuts import Shortcuts, ShortcutAction

class ActionManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions: Dict[ShortcutAction, QAction] = {}
        
    def setup_actions(self, window: QWidget, shortcuts: Shortcuts, 
                      file_manager, view_manager, nav_bar, tab_manager, undo_manager):
        """
        Creates all actions based on the Shortcuts model and registers them.
        """
        
        # Mapping: Enum -> (Icon Name, Display Text, Slot Function)
        # Note: Slot can be None if implemented elsewhere or TODO
        bindings: Dict[ShortcutAction, Tuple[str, str, Callable]] = {
            # --- File Operations ---
            ShortcutAction.COPY:            ("edit-copy", "Copy", file_manager.copy_selection),
            ShortcutAction.CUT:             ("edit-cut", "Cut", file_manager.cut_selection),
            ShortcutAction.PASTE:           ("edit-paste", "Paste", file_manager.paste_to_current),
            ShortcutAction.TRASH:           ("user-trash", "Move to Trash", file_manager.trash_selection),
            ShortcutAction.RENAME:          ("edit-rename", "Rename", file_manager.rename_selection),
            ShortcutAction.DUPLICATE:       ("edit-copy", "Duplicate", file_manager.duplicate_selection),
            ShortcutAction.NEW_FOLDER:      ("folder-new", "New Folder", file_manager.create_new_folder),
            ShortcutAction.DELETE_PERMANENT:("edit-delete", "Delete Permanently", None), 
            
            # --- Undo / Redo ---
            ShortcutAction.UNDO:            ("edit-undo", "Undo", undo_manager.undo),
            ShortcutAction.REDO:            ("edit-redo", "Redo", undo_manager.redo),

            # --- Navigation ---
            ShortcutAction.GO_UP:           ("go-up", "Go Up", window.go_up),
            ShortcutAction.GO_BACK:         ("go-previous", "Back", tab_manager.go_back),
            ShortcutAction.GO_FORWARD:      ("go-next", "Forward", tab_manager.go_forward),
            ShortcutAction.GO_HOME:         ("go-home", "Home", tab_manager.go_home),
            ShortcutAction.REFRESH:         ("view-refresh", "Refresh", lambda: tab_manager.current_tab.scanner.scan_directory(tab_manager.current_tab.current_path) if tab_manager.current_tab else None),
            ShortcutAction.FOCUS_PATH_BAR:  ("", "Focus Path Bar", nav_bar.focus_path),
            ShortcutAction.FIND:            ("edit-find", "Find", nav_bar.focus_path),

            # --- View ---
            ShortcutAction.TOGGLE_HIDDEN:   ("view-hidden", "Toggle Hidden Files", view_manager.toggle_hidden),
            ShortcutAction.ZOOM_IN:         ("zoom-in", "Zoom In", view_manager.zoom_in),
            ShortcutAction.ZOOM_OUT:        ("zoom-out", "Zoom Out", view_manager.zoom_out),
            ShortcutAction.ZOOM_RESET:      ("zoom-original", "Reset Zoom", view_manager.reset_zoom),
            ShortcutAction.SELECT_ALL:      ("edit-select-all", "Select All", view_manager.select_all),

            # --- Tabs ---
            ShortcutAction.NEW_TAB:         ("tab-new", "New Tab", lambda: tab_manager.add_tab()),
            ShortcutAction.CLOSE_TAB:       ("tab-close", "Close Tab", lambda: tab_manager.close_current_tab()),
            ShortcutAction.NEXT_TAB:        ("", "Next Tab", tab_manager.next_tab),
            ShortcutAction.PREV_TAB:        ("", "Previous Tab", tab_manager.prev_tab),
        }

        # Factory Loop
        for action_enum, (icon_name, text, slot) in bindings.items():
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
