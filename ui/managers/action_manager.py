"""
ActionManager — Central Hub for UI Actions and Shortcuts

Defines all QActions, their icons, shortcuts, and connects them to logic.
Replaces ShortcutsModel and manual QAction creation in MainWindow.
"""

from PySide6.QtCore import QObject, Signal, Slot, QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence, QIcon, QShortcut
from PySide6.QtWidgets import QWidget
from typing import Dict, Callable, Optional

class ActionManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions: Dict[str, QAction] = {}
        self._settings = QSettings("Imbric", "Shortcuts")
        
    def setup_actions(self, window: QWidget, file_manager, view_manager, nav_bar, tab_manager):
        """
        Creates all actions and registers them to the window.
        """
        # --- File Operations ---
        self._add("copy", "Copy", "edit-copy", "Ctrl+C", file_manager.copy_selection)
        self._add("cut", "Cut", "edit-cut", "Ctrl+X", file_manager.cut_selection)
        self._add("paste", "Paste", "edit-paste", "Ctrl+V", file_manager.paste_to_current)
        self._add("trash", "Move to Trash", "user-trash", "Delete", file_manager.trash_selection)
        self._add("rename", "Rename", "edit-rename", "F2", file_manager.rename_selection)
        self._add("duplicate", "Duplicate", "edit-copy", "Ctrl+D", file_manager.duplicate_selection)
        self._add("delete_permanent", "Delete Permanently", "edit-delete", "Shift+Delete", None) # TODO: Implement permanent delete
        self._add("new_folder", "New Folder", "folder-new", "Ctrl+Shift+N", file_manager.create_new_folder)
        
        # --- Navigation ---
        self._add("go_up", "Go Up", "go-up", "Backspace", window.go_up)
        self._add("go_back", "Back", "go-previous", "Alt+Left", tab_manager.go_back)
        self._add("go_forward", "Forward", "go-next", "Alt+Right", tab_manager.go_forward)
        self._add("go_home", "Home", "go-home", "Alt+Home", tab_manager.go_home)
        self._add("refresh", "Refresh", "view-refresh", "F5", lambda: tab_manager.current_tab.scanner.scan_directory(tab_manager.current_tab.current_path) if tab_manager.current_tab else None)
        self._add("focus_path", "Focus Path Bar", "", "Ctrl+L", nav_bar.focus_path)
        self._add("find", "Find", "edit-find", "Ctrl+F", nav_bar.focus_path)
        
        # --- View ---
        self._add("toggle_hidden", "Toggle Hidden Files", "view-hidden", "Ctrl+H", view_manager.toggle_hidden)
        self._add("zoom_in", "Zoom In", "zoom-in", "Ctrl+=", view_manager.zoom_in)
        self._add("zoom_out", "Zoom Out", "zoom-out", "Ctrl+-", view_manager.zoom_out)
        self._add("zoom_reset", "Reset Zoom", "zoom-original", "Ctrl+0", view_manager.reset_zoom)
        self._add("select_all", "Select All", "edit-select-all", "Ctrl+A", view_manager.select_all)
        
        # --- Tabs ---
        self._add("new_tab", "New Tab", "tab-new", "Ctrl+T", lambda: tab_manager.add_tab())
        self._add("close_tab", "Close Tab", "tab-close", "Ctrl+W", lambda: tab_manager.close_current_tab())
        self._add("next_tab", "Next Tab", "", "Ctrl+Tab", tab_manager.next_tab)
        self._add("prev_tab", "Previous Tab", "", "Ctrl+Shift+Tab", tab_manager.prev_tab)
        
        # Add all actions to window so global shortcuts work
        window.addActions(list(self._actions.values()))
        
    def _add(self, name: str, text: str, icon_name: str, default_shortcut: str, slot: Callable):
        """Helper to create and register an action."""
        action = QAction(text, self.parent())
        if icon_name:
            action.setIcon(QIcon.fromTheme(icon_name))
            
        # Load shortcut from settings or use default
        shortcut_key = self._settings.value(f"KeyBindings/{name}", default_shortcut)
        if shortcut_key:
            action.setShortcut(QKeySequence(shortcut_key))
            
        action.setShortcutContext(Qt.WindowShortcut)
        
        if slot:
            action.triggered.connect(slot)
            
        self._actions[name] = action
        return action

    def get_action(self, name: str) -> Optional[QAction]:
        return self._actions.get(name)
