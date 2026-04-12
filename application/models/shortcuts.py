"""
Shortcuts Model — Centralized Keyboard Configuration

Features:
- Pure data model (No QAction/QWidget logic)
- QSettings persistence
- Enum-based type safety
- Conflict detection
"""

from PySide6.QtCore import QObject, Signal, QSettings
from enum import Enum, auto
from typing import Dict, Optional


class ShortcutAction(Enum):
    """All available shortcut actions."""
    # File Operations
    COPY = auto()
    CUT = auto()
    PASTE = auto()
    TRASH = auto()
    DELETE_PERMANENT = auto()
    RENAME = auto()
    DUPLICATE = auto()
    NEW_FOLDER = auto()
    NEW_FILE = auto()
    
    # Selection
    SELECT_ALL = auto()
    DESELECT_ALL = auto()
    INVERT_SELECTION = auto()
    
    # Navigation
    GO_UP = auto()
    GO_BACK = auto()
    GO_FORWARD = auto()
    GO_HOME = auto()
    FOCUS_PATH_BAR = auto()
    OPEN_SELECTED = auto()
    REFRESH = auto()
    
    # View
    ZOOM_IN = auto()
    ZOOM_OUT = auto()
    ZOOM_RESET = auto()
    TOGGLE_HIDDEN = auto()
    
    # Tabs
    NEW_TAB = auto()
    CLOSE_TAB = auto()
    NEXT_TAB = auto()
    PREV_TAB = auto()
    
    # Undo/Redo
    UNDO = auto()
    REDO = auto()
    
    # Search
    FIND = auto()


# Default shortcut mappings
DEFAULT_SHORTCUTS: Dict[ShortcutAction, str] = {
    # File Operations
    ShortcutAction.COPY: "Ctrl+C",
    ShortcutAction.CUT: "Ctrl+X",
    ShortcutAction.PASTE: "Ctrl+V",
    ShortcutAction.TRASH: "Delete",
    ShortcutAction.DELETE_PERMANENT: "Shift+Delete",
    ShortcutAction.RENAME: "F2",
    ShortcutAction.DUPLICATE: "Ctrl+D",
    ShortcutAction.NEW_FOLDER: "Ctrl+Shift+N",
    ShortcutAction.NEW_FILE: "Ctrl+Alt+N",
    
    # Selection
    ShortcutAction.SELECT_ALL: "Ctrl+A",
    ShortcutAction.DESELECT_ALL: "Escape",
    ShortcutAction.INVERT_SELECTION: "Ctrl+I",
    
    # Navigation
    ShortcutAction.GO_UP: "Backspace",
    ShortcutAction.GO_BACK: "Alt+Left",
    ShortcutAction.GO_FORWARD: "Alt+Right",
    ShortcutAction.GO_HOME: "Alt+Home",
    ShortcutAction.FOCUS_PATH_BAR: "Ctrl+L",
    ShortcutAction.OPEN_SELECTED: "Return",
    ShortcutAction.REFRESH: "F5",
    
    # View
    ShortcutAction.ZOOM_IN: "Ctrl+=",
    ShortcutAction.ZOOM_OUT: "Ctrl+-",
    ShortcutAction.ZOOM_RESET: "Ctrl+0",
    ShortcutAction.TOGGLE_HIDDEN: "Ctrl+H",
    
    # Tabs
    ShortcutAction.NEW_TAB: "Ctrl+T",
    ShortcutAction.CLOSE_TAB: "Ctrl+W",
    ShortcutAction.NEXT_TAB: "Ctrl+Tab",
    ShortcutAction.PREV_TAB: "Ctrl+Shift+Tab",
    
    # Undo/Redo
    ShortcutAction.UNDO: "Ctrl+Z",
    ShortcutAction.REDO: "Ctrl+Shift+Z",
    
    # Search
    ShortcutAction.FIND: "Ctrl+F",
}


class Shortcuts(QObject):
    """
    Manages persistence and lookup for keyboard shortcuts.
    Pure Data model: Does NOT create QActions or UI elements.
    """
    
    # Emitted when configuration changes (e.g. from Settings Dialog)
    configChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcuts: Dict[ShortcutAction, str] = DEFAULT_SHORTCUTS.copy()
        self._settings = QSettings("Imbric", "Shortcuts")
        self.load()
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    def get(self, action: ShortcutAction) -> str:
        """Get the current key sequence for an action."""
        return self._shortcuts.get(action, "")
    
    def set(self, action: ShortcutAction, key_sequence: str):
        """Change a shortcut's key binding."""
        self._shortcuts[action] = key_sequence
        self.save()
        self.configChanged.emit()
    
    def reset(self, action: ShortcutAction = None):
        """Reset to defaults."""
        if action:
            default_key = DEFAULT_SHORTCUTS.get(action, "")
            self.set(action, default_key)
        else:
            for act, key in DEFAULT_SHORTCUTS.items():
                self._shortcuts[act] = key
            self.save()
            self.configChanged.emit()
    
    def save(self):
        """Persist current shortcuts to QSettings."""
        self._settings.beginGroup("KeyBindings")
        for action, key in self._shortcuts.items():
            self._settings.setValue(action.name, key)
        self._settings.endGroup()
        self._settings.sync()
    
    def load(self):
        """Load shortcuts from QSettings."""
        self._settings.beginGroup("KeyBindings")
        keys = self._settings.childKeys()
        for key_name in keys:
            try:
                # Key names match Enum names (e.g. "COPY")
                action = ShortcutAction[key_name]
                sequence = self._settings.value(key_name)
                # Allow empty strings (unbound)
                if sequence is not None:
                    self._shortcuts[action] = str(sequence)
            except KeyError:
                pass # Stale key in settings
        self._settings.endGroup()
    
    def get_conflicts(self) -> Dict[str, list]:
        """Find key sequences assigned to multiple actions."""
        reverse_map = {}
        conflicts = {}
        
        for action, key in self._shortcuts.items():
            if not key: continue
            if key in reverse_map:
                reverse_map[key].append(action)
            else:
                reverse_map[key] = [action]
        
        for key, actions in reverse_map.items():
            if len(actions) > 1:
                conflicts[key] = actions
                
        return conflicts
