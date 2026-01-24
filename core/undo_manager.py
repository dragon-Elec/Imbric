"""
[DONE] UndoManager — Undo/Redo Stack for File Operations

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
import os


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
    
    # Emitted when a shortcut is triggered (we can reuse this pattern or specific signals)
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
        if not operation:
            return

        # Simple validation
        required_keys = ["type", "src"]
        if not all(k in operation for k in required_keys):
            print(f"[UndoManager] Invalid operation pushed: {operation}")
            return

        self._undo_stack.append(operation)
        
        # Limit history size
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)  # Remove oldest
            
        # Clear redo stack on new action (standard undo/redo behavior)
        self._redo_stack.clear()
        
        self._emit_availability()
        print(f"[UndoManager] Pushed: {operation['type']} {operation['src']}")
    
    @Slot()
    def undo(self) -> bool:
        """
        Undo the last operation.
        
        Returns:
            True if undo was successful, False if stack empty or failed
        """
        if not self.canUndo():
            return False
            
        op = self._undo_stack.pop()
        
        # Calculate inverse operation
        inverse_op = self._reverse_operation(op)
        if not inverse_op:
            print(f"[UndoManager] Could not determine inverse for {op}")
            # Put it back? Or just fail? For now, fail but keep state consistent?
            # Actually, if we fail to reverse, it's safer to NOT put it back effectively "consuming" the undo.
            self._emit_availability()
            return False
            
        print(f"[UndoManager] Undoing {op['type']} -> Executing {inverse_op['type']}")
        
        # Execute the inverse
        success = self._execute(inverse_op)
        
        if success:
            # Add ORIGINAL op to redo stack, so we can redo (re-apply) it later
            self._redo_stack.append(op)
            self.operationUndone.emit(f"Undid {op['type']}")
        else:
            # If execution failed, what do we do?
            # Maybe push op back to undo stack?
            self._undo_stack.append(op) 
            
        self._emit_availability()
        return success
    
    @Slot()
    def redo(self) -> bool:
        """
        Redo the last undone operation.
        
        Returns:
            True if redo was successful, False if stack empty or failed
        """
        if not self.canRedo():
            return False
            
        op = self._redo_stack.pop()
        
        print(f"[UndoManager] Redoing {op['type']}")
        
        # Execute original operation again
        success = self._execute(op)
        
        if success:
            # Push back to undo stack
            self._undo_stack.append(op)
            self.operationRedone.emit(f"Redid {op['type']}")
        else:
            # Push back to redo stack if failed?
            self._redo_stack.append(op)
            
        self._emit_availability()
        return success
    
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
        op_type = op.get("type")
        src = op.get("src")
        # For Move/Copy/Rename, the 'result path' (e.g. if renamed to 'A (2)') 
        # should be stored in 'dest' or a specific 'result_path' field. 
        # We assume 'dest' contains the FINAL path where the item ended up.
        dest = op.get("dest") 
        
        if op_type == "rename":
            # Reverse: Rename dest back to original name
            # op: {type: rename, src: /dir/old.txt, dest: /dir/new.txt}
            # rev: {type: rename, src: /dir/new.txt, dest: old.txt}
            # FileOperations.rename(path, new_name) takes basename only for new_name.
            return {
                "type": "rename",
                "src": dest,
                "dest": os.path.basename(src)
            }
            
        elif op_type == "move":
            # Reverse: Move dest back to original src location
            # op: {type: move, src: /A/file.txt, dest: /B/file.txt}
            # rev: {type: move, src: /B/file.txt, dest: /A/file.txt}
            # Note: We pass the FULL original path, not just the directory.
            # FileOperations.move(src, dest) where dest is the target FILE path.
            return {
                "type": "move",
                "src": dest,
                "dest": src  # Full original path
            }
            
        elif op_type == "copy":
            # Reverse: Trash the copy
            # op: {type: copy, src: /A, dest: /B/A}
            # rev: {type: trash, src: /B/A}
            return {
                "type": "trash",
                "src": dest
            }
            
        elif op_type == "trash":
            # Reverse: Restore from trash
            # This is hard without specific "trash info".
            # For now, we will mark this as unsupported or use a specific restore command if we add it.
            # Assuming we can't easily undo trash without 'gio restore' logic which isn't in FileOperations yet.
            print("[UndoManager] Undo Trash not yet fully supported (requires Trash restoration logic)")
            return None # TODO: Implement Restore
            
        elif op_type == "createFolder":
            # Reverse: Trash the created folder
            # op: {type: createFolder, src: /path/NewFolder}
            # rev: {type: trash, src: /path/NewFolder}
            return {
                "type": "trash",
                "src": src
            }
            
        return None
    
    def _execute(self, op: dict) -> bool:
        """Execute an operation using FileOperations."""
        if not self._file_ops:
            print("[UndoManager] No FileOperations instance connected")
            return False
            
        op_type = op.get("type")
        src = op.get("src")
        dest = op.get("dest")
        
        # We need to map 'dest' correctly for FileOperations methods
        
        if op_type == "rename":
            # Note: FileOperations is async. We return True optimistically.
            # If the operation fails, the redo stack will have a bad entry.
            # TODO: Implement proper async completion tracking.
            self._file_ops.rename(src, dest)
            return True
            
        elif op_type == "move":
            self._file_ops.move(src, dest)
            return True
            
        elif op_type == "copy":
            self._file_ops.copy(src, dest)
            return True
            
        elif op_type == "trash":
            self._file_ops.trash(src)
            return True
            
        elif op_type == "createFolder":
            self._file_ops.createFolder(src)
            return True
            
        return False
    
    def _emit_availability(self):
        """Update UI about undo/redo availability."""
        self.undoAvailable.emit(self.canUndo())
        self.redoAvailable.emit(self.canRedo())
