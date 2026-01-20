"""
[STUB] UndoManager — Undo/Redo Stack for File Operations

Tracks file operations (copy, move, rename, trash, create) and allows
reversing them. Each operation is recorded with enough info to undo it.

Usage:
    undo_mgr = UndoManager()
    undo_mgr.push({"type": "rename", "old": "/path/old.txt", "new": "/path/new.txt"})
    undo_mgr.undo()  # Renames back to old.txt
    undo_mgr.redo()  # Renames back to new.txt
    
Integration:
    - FileOperations should call undo_mgr.push() after each successful op
    - MainWindow connects Ctrl+Z to undo(), Ctrl+Shift+Z to redo()
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import Optional


class UndoManager(QObject):
    """
    Manages undo/redo stack for file operations.
    
    Operation dict format:
        {
            "type": "copy" | "move" | "rename" | "trash" | "createFolder",
            "src": str,       # Original path
            "dest": str,      # Destination path (for copy/move/rename)
            "timestamp": float
        }
    """
    
    # Signals for UI buttons (enable/disable)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    
    # Signal when operation is undone/redone (for status bar)
    operationUndone = Signal(str)  # Description of what was undone
    operationRedone = Signal(str)  # Description of what was redone
    
    def __init__(self, file_operations=None, parent=None):
        """
        Args:
            file_operations: Reference to FileOperations for executing undo actions
        """
        super().__init__(parent)
        self._undo_stack = []
        self._redo_stack = []
        self._file_ops = file_operations
        self._max_history = 50  # Limit memory usage
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(dict)
    def push(self, operation: dict):
        """
        Record an operation for undo.
        Call this AFTER a successful file operation.
        
        Args:
            operation: Dict with keys "type", "src", "dest" (optional), "timestamp"
        """
        raise NotImplementedError("TODO: Implement - Add to undo stack, clear redo stack")
    
    @Slot()
    def undo(self) -> bool:
        """
        Undo the last operation.
        
        Returns:
            True if undo was successful, False if stack empty or failed
        """
        raise NotImplementedError("TODO: Implement - Pop from undo, reverse op, push to redo")
    
    @Slot()
    def redo(self) -> bool:
        """
        Redo the last undone operation.
        
        Returns:
            True if redo was successful, False if stack empty or failed
        """
        raise NotImplementedError("TODO: Implement - Pop from redo, execute op, push to undo")
    
    @Slot(result=bool)
    def canUndo(self) -> bool:
        """Returns True if there are operations to undo."""
        return len(self._undo_stack) > 0
    
    @Slot(result=bool)
    def canRedo(self) -> bool:
        """Returns True if there are operations to redo."""
        return len(self._redo_stack) > 0
    
    @Slot()
    def clear(self):
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.undoAvailable.emit(False)
        self.redoAvailable.emit(False)
    
    # -------------------------------------------------------------------------
    # INTERNAL
    # -------------------------------------------------------------------------
    
    def _reverse_operation(self, op: dict) -> Optional[dict]:
        """
        Create the inverse operation.
        
        Examples:
            rename(A→B) → rename(B→A)
            move(A→B) → move(B→A)  
            copy(A→B) → trash(B)
            trash(A) → restore(A) [needs trash location tracking]
            createFolder(A) → trash(A)
        """
        raise NotImplementedError("TODO: Implement - Return inverse operation dict")
    
    def _execute(self, op: dict) -> bool:
        """Execute an operation using FileOperations."""
        raise NotImplementedError("TODO: Implement - Call appropriate file_ops method")
    
    def _emit_availability(self):
        """Update UI about undo/redo availability."""
        self.undoAvailable.emit(self.canUndo())
        self.redoAvailable.emit(self.canRedo())
