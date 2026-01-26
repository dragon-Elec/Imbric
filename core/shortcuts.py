"""
[STUB] Shortcuts — Centralized Keyboard Shortcut Definitions

Single source of truth for all keyboard shortcuts.
Allows easy customization and conflict detection.

Usage:
    from core.shortcuts import Shortcuts, ShortcutAction
    
    shortcuts = Shortcuts()
    shortcuts.setup(main_window)
    
    # Later, to customize:
    shortcuts.set("select_all", "Ctrl+Shift+A")
    
Integration:
    - MainWindow calls shortcuts.setup() during init
    - Custom shortcuts dialog reads/writes via this class
    - Shortcuts persisted to QSettings
"""

from PySide6.QtCore import QObject, Signal, Slot, QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtWidgets import QWidget
from enum import Enum, auto
from typing import Dict, Callable, Optional


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
    
    # View
    ZOOM_IN = auto()
    ZOOM_OUT = auto()
    ZOOM_RESET = auto()
    TOGGLE_HIDDEN = auto()
    REFRESH = auto()
    
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
    
    # View
    ShortcutAction.ZOOM_IN: "Ctrl+=",
    ShortcutAction.ZOOM_OUT: "Ctrl+-",
    ShortcutAction.ZOOM_RESET: "Ctrl+0",
    ShortcutAction.TOGGLE_HIDDEN: "Ctrl+H",
    ShortcutAction.REFRESH: "F5",
    
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
    Manages all keyboard shortcuts for the application.
    """
    
    # Emitted when a shortcut is triggered
    shortcutTriggered = Signal(ShortcutAction)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcuts: Dict[ShortcutAction, str] = DEFAULT_SHORTCUTS.copy()
        self._actions: Dict[ShortcutAction, QAction] = {}
        self._handlers: Dict[ShortcutAction, list] = {} # List of handlers
        self._settings = QSettings("Imbric", "Shortcuts")
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    def setup(self, window: QWidget):
        """
        Create all shortcuts and attach to the window.
        Call this once during MainWindow initialization.
        """
        self.load() # Load custom shortcuts first
        
        for action_enum, key_seq in self._shortcuts.items():
            action = QAction(window)
            action.setShortcut(QKeySequence(key_seq))
            action.setShortcutContext(Qt.WindowShortcut if "Ctrl" in key_seq else Qt.WidgetWithChildrenShortcut)
            # Default to WindowShortcut context for most things, but some might need tuning.
            # Actually, using ShortcutContext.WindowShortcut is usually best for global app shortcuts.
            action.setShortcutContext(Qt.WindowShortcut)
            
            # Connect internal trigger to emit signal
            # We use a lambda to capture the enum value
            action.triggered.connect(lambda checked=False, a=action_enum: self._on_triggered(a))
            
            window.addAction(action)
            self._actions[action_enum] = action
            
    def _on_triggered(self, action_enum: ShortcutAction):
        """Internal handler to emit signal and call registered handlers."""
        self.shortcutTriggered.emit(action_enum)
        if action_enum in self._handlers:
            for handler in self._handlers[action_enum]:
                handler()

    def connect(self, action: ShortcutAction, handler: Callable):
        """
        Connect a handler function to a shortcut action.
        
        Args:
            action: The ShortcutAction to handle
            handler: Callable to invoke when shortcut triggered
        """
        if action not in self._handlers:
            self._handlers[action] = []
        self._handlers[action].append(handler)
    
    def set(self, action: ShortcutAction, key_sequence: str):
        """
        Change a shortcut's key binding.
        
        Args:
            action: The action to rebind
            key_sequence: New key sequence (e.g., "Ctrl+Shift+A")
        """
        self._shortcuts[action] = key_sequence
        if action in self._actions:
            self._actions[action].setShortcut(QKeySequence(key_sequence))
        self.save()
    
    def get(self, action: ShortcutAction) -> str:
        """Get the current key sequence for an action."""
        return self._shortcuts.get(action, "")
    
    def reset(self, action: ShortcutAction = None):
        """
        Reset shortcut(s) to defaults.
        If action is None, resets all shortcuts.
        """
        if action:
            default_key = DEFAULT_SHORTCUTS.get(action, "")
            self.set(action, default_key)
        else:
            for act, key in DEFAULT_SHORTCUTS.items():
                self.set(act, key)
    
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
            # key_name matches ShortcutAction.name (e.g., "COPY")
            try:
                action = ShortcutAction[key_name]
                sequence = self._settings.value(key_name)
                if sequence:
                    self._shortcuts[action] = str(sequence)
            except KeyError:
                pass # Unknown action in settings
        self._settings.endGroup()
    
    def get_conflicts(self) -> Dict[str, list]:
        """
        Find shortcut conflicts (same key bound to multiple actions).
        
        Returns:
            Dict mapping key_sequence to list of interacting actions
        """
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
