"""
NavigationManager — History and Path Management

Handles:
- Back/Forward stacks
- Current path tracking
- Navigation signals
"""

from PySide6.QtCore import QObject, Signal, Slot, Property

class NavigationManager(QObject):
    """
    Manages navigation history (back/forward stacks) and current path state.
    Designed to be used per-tab or globally depending on application structure.
    """
    canGoBackChanged = Signal()
    canGoForwardChanged = Signal()
    currentPathChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._back_stack: list[str] = []
        self._forward_stack: list[str] = []
        self._current_path: str = ""

    @Property(bool, notify=canGoBackChanged)
    def canGoBack(self) -> bool:
        return len(self._back_stack) > 0

    @Property(bool, notify=canGoForwardChanged)
    def canGoForward(self) -> bool:
        return len(self._forward_stack) > 0

    @Property(str, notify=currentPathChanged)
    def currentPath(self) -> str:
        return self._current_path

    @Slot(str)
    def navigate(self, path: str) -> None:
        """Navigates to a new path, pushing the current one to history."""
        if not path or path == self._current_path:
            return
            
        if self._current_path:
            self._back_stack.append(self._current_path)
            self.canGoBackChanged.emit()
            
        # Clear forward stack on new navigation
        if self._forward_stack:
            self._forward_stack.clear()
            self.canGoForwardChanged.emit()
        
        self._current_path = path
        self.currentPathChanged.emit(path)

    @Slot()
    def back(self) -> None:
        """Navigates to the previous path in history."""
        if not self._back_stack:
            return
            
        # Push current to forward
        if self._current_path:
            self._forward_stack.append(self._current_path)
            self.canGoForwardChanged.emit()
            
        # Pop from back
        self._current_path = self._back_stack.pop()
        self.canGoBackChanged.emit()
        
        self.currentPathChanged.emit(self._current_path)

    @Slot()
    def forward(self) -> None:
        """Navigates to the next path in history."""
        if not self._forward_stack:
            return
            
        # Push current to back
        if self._current_path:
            self._back_stack.append(self._current_path)
            self.canGoBackChanged.emit()
            
        # Pop from forward
        self._current_path = self._forward_stack.pop()
        self.canGoForwardChanged.emit()
        
        self.currentPathChanged.emit(self._current_path)
