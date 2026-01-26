"""
[DONE] UndoManager — Async-Aware Undo/Redo Stack for File Operations

Tracks file operations (copy, move, rename, trash, create) and allows
reversing them. Uses event-driven pattern to properly handle async I/O.

Architecture:
    1. undo() pops from stack but DOESN'T push to redo yet
    2. Queues operation and tracks it as "pending"
    3. Waits for FileOperations.operationFinished signal
    4. On success: pushes to redo stack
    5. On failure: pushes back to undo stack

Usage:
    undo_mgr = UndoManager(file_operations=file_ops)
    undo_mgr.undo()  # Async - will emit operationUndone when complete
    
Integration:
    - TransactionManager pushes completed Transactions via historyCommitted signal
    - MainWindow connects Ctrl+Z to undo(), Ctrl+Shift+Z to redo()
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import Optional, Dict, Any
from enum import Enum
import os


class PendingMode(Enum):
    """Tracks whether we're in an undo or redo operation."""
    NONE = 0
    UNDO = 1
    REDO = 2


class UndoManager(QObject):
    """
    Manages undo/redo stack for file operations.
    
    Async-aware: Waits for operation completion before transitioning stacks.
    """
    
    # Signals for UI buttons (enable/disable)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    
    # Signal when operation is undone/redone (for status bar)
    operationUndone = Signal(str)  # Description of what was undone
    operationRedone = Signal(str)  # Description of what was redone
    
    # Signal when undo/redo fails
    undoFailed = Signal(str)  # Error message
    
    # Signal when busy (disable undo button during operation)
    busyChanged = Signal(bool)
    
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
        
        # Async state tracking
        self._pending_operation = None  # The operation we're currently undoing/redoing
        self._pending_mode = PendingMode.NONE
        self._pending_job_ids = set()  # Track job IDs for this undo/redo
        self._pending_success = True  # Track if any operation failed
        self._expected_completions = 0  # How many ops we're waiting for
        self._received_completions = 0
        
        # Connect to FileOperations signals if available
        if self._file_ops:
            self._file_ops.operationFinished.connect(self._on_operation_finished)
    
    def setFileOperations(self, file_ops):
        """Set or update the FileOperations reference."""
        # Disconnect from old
        if self._file_ops:
            try:
                self._file_ops.operationFinished.disconnect(self._on_operation_finished)
            except RuntimeError:
                pass  # Was not connected
        
        self._file_ops = file_ops
        
        # Connect to new
        if self._file_ops:
            self._file_ops.operationFinished.connect(self._on_operation_finished)
    
    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------
    
    @Slot(object)
    def push(self, operation):
        """
        Record a Transaction object for undo.
        Call this AFTER a batch of operations (Transaction) is committed.
        
        Args:
            operation: Transaction object or dict with keys "type", "src", "dest"
        """
        if not operation:
            return

        # Simple validation for dict
        if isinstance(operation, dict):
            required_keys = ["type", "src"]
            if not all(k in operation for k in required_keys):
                print(f"[UndoManager] Invalid operation pushed: {operation}")
                return

        self._undo_stack.append(operation)
        
        # Limit history size
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)  # Remove oldest
            
        # Clear redo stack on new action
        self._redo_stack.clear()
        
        self._emit_availability()
        
        # Log info
        desc = operation.description if hasattr(operation, 'description') else str(operation)
        print(f"[UndoManager] Pushed: {desc}")
    
    @Slot(result=bool)
    def undo(self) -> bool:
        """
        Undo the last operation (async).
        
        Returns:
            True if undo was started, False if stack empty or busy
        """
        if not self.canUndo():
            return False
        
        if self._pending_mode != PendingMode.NONE:
            print("[UndoManager] Already processing an undo/redo")
            return False
            
        op = self._undo_stack.pop()
        desc = op.description if hasattr(op, 'description') else str(op)
        print(f"[UndoManager] Undoing: {desc}")
        
        # Set pending state BEFORE executing
        self._pending_operation = op
        self._pending_mode = PendingMode.UNDO
        self._pending_job_ids.clear()
        self._pending_success = True
        self._received_completions = 0
        
        self.busyChanged.emit(True)
        self._emit_availability()
        
        # Count expected completions
        if isinstance(op, dict):
            self._expected_completions = 1
        else:
            self._expected_completions = len(op.ops)
        
        # Execute the inverse operations
        success = self._undo_transaction(op)
        
        if not success:
            # Failed to even start the operation (e.g., no FileOperations)
            self._pending_operation = None
            self._pending_mode = PendingMode.NONE
            self._undo_stack.append(op)  # Put it back
            self.busyChanged.emit(False)
            self._emit_availability()
            return False
        
        # If no async operations were started, complete immediately
        if self._expected_completions == 0:
            self._finalize_pending()
        
        return True
    
    @Slot(result=bool)
    def redo(self) -> bool:
        """
        Redo the last undone operation (async).
        
        Returns:
            True if redo was started, False if stack empty or busy
        """
        if not self.canRedo():
            return False
            
        if self._pending_mode != PendingMode.NONE:
            print("[UndoManager] Already processing an undo/redo")
            return False
            
        op = self._redo_stack.pop()
        desc = op.description if hasattr(op, 'description') else str(op)
        print(f"[UndoManager] Redoing: {desc}")
        
        # Set pending state
        self._pending_operation = op
        self._pending_mode = PendingMode.REDO
        self._pending_job_ids.clear()
        self._pending_success = True
        self._received_completions = 0
        
        self.busyChanged.emit(True)
        self._emit_availability()
        
        # Count expected completions
        if isinstance(op, dict):
            self._expected_completions = 1
        else:
            self._expected_completions = len(op.ops)
        
        # Execute the original operations
        success = self._redo_transaction(op)
        
        if not success:
            self._pending_operation = None
            self._pending_mode = PendingMode.NONE
            self._redo_stack.append(op)
            self.busyChanged.emit(False)
            self._emit_availability()
            return False
        
        if self._expected_completions == 0:
            self._finalize_pending()
            
        return True
    
    @Slot(result=bool)
    def canUndo(self) -> bool:
        """Returns True if there are operations to undo and not busy."""
        return len(self._undo_stack) > 0 and self._pending_mode == PendingMode.NONE
    
    @Slot(result=bool)
    def canRedo(self) -> bool:
        """Returns True if there are operations to redo and not busy."""
        return len(self._redo_stack) > 0 and self._pending_mode == PendingMode.NONE
    
    @Slot(result=bool)
    def isBusy(self) -> bool:
        """Returns True if an undo/redo is in progress."""
        return self._pending_mode != PendingMode.NONE
    
    @Slot()
    def clear(self):
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pending_operation = None
        self._pending_mode = PendingMode.NONE
        self.undoAvailable.emit(False)
        self.redoAvailable.emit(False)
    
    # -------------------------------------------------------------------------
    # SIGNAL HANDLER (Async completion)
    # -------------------------------------------------------------------------
    
    @Slot(str, str, str, str, bool, str)
    def _on_operation_finished(self, tid: str, job_id: str, op_type: str, 
                                result_path: str, success: bool, message: str):
        """
        Called when any file operation completes.
        We check if it's one of our pending undo/redo operations.
        """
        if self._pending_mode == PendingMode.NONE:
            return  # Not our operation
        
        if job_id in self._pending_job_ids:
            self._pending_job_ids.discard(job_id)
            self._received_completions += 1
            
            if not success:
                self._pending_success = False
                print(f"[UndoManager] Operation failed: {message}")
            
            # Check if all operations completed
            if self._received_completions >= self._expected_completions:
                self._finalize_pending()
    
    def _finalize_pending(self):
        """Complete the pending undo/redo operation."""
        op = self._pending_operation
        mode = self._pending_mode
        success = self._pending_success
        
        # Reset state
        self._pending_operation = None
        self._pending_mode = PendingMode.NONE
        self._pending_job_ids.clear()
        
        self.busyChanged.emit(False)
        
        desc = op.description if hasattr(op, 'description') else "Operation"
        
        if mode == PendingMode.UNDO:
            if success:
                self._redo_stack.append(op)
                self.operationUndone.emit(f"Undid {desc}")
            else:
                self._undo_stack.append(op)  # Put it back
                self.undoFailed.emit(f"Failed to undo {desc}")
        
        elif mode == PendingMode.REDO:
            if success:
                self._undo_stack.append(op)
                self.operationRedone.emit(f"Redid {desc}")
            else:
                self._redo_stack.append(op)  # Put it back
                self.undoFailed.emit(f"Failed to redo {desc}")
        
        self._emit_availability()
    
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
            trash(A) → restore(A)
            createFolder(A) → trash(A)
        """
        op_type = op.get("type")
        src = op.get("src")
        dest = op.get("dest") 
        
        if op_type == "rename":
            return {
                "type": "rename",
                "src": dest,
                "dest": os.path.basename(src)
            }
            
        elif op_type == "move":
            return {
                "type": "move",
                "src": dest,
                "dest": src
            }
            
        elif op_type == "copy":
            return {
                "type": "trash",
                "src": dest
            }
            
        elif op_type == "trash":
            return {
                "type": "restore_trash",
                "src": src
            }
            
        elif op_type == "createFolder":
            return {
                "type": "trash",
                "src": src
            }
            
        return None
    
    def _undo_transaction(self, tx) -> bool:
        """
        Reverses a Transaction (or single op dict).
        Iterates operations in LIFO order.
        """
        # Handle legacy dict
        if isinstance(tx, dict):
            inv = self._reverse_operation(tx)
            return self._execute_single_op(inv) if inv else False

        # Handle Transaction Object
        ops_to_undo = list(reversed(tx.ops))
        
        if not ops_to_undo:
            return True  # Empty transaction
        
        all_started = True
        for op in ops_to_undo:
            op_dict = {
                "type": op.op_type,
                "src": op.src,
                "dest": op.dest if op.dest else op.result_path
            }
            
            inv = self._reverse_operation(op_dict)
            if inv:
                if not self._execute_single_op(inv):
                    all_started = False
            else:
                all_started = False
        
        return all_started

    def _redo_transaction(self, tx) -> bool:
        """Re-applies a Transaction."""
        if isinstance(tx, dict):
            return self._execute_single_op(tx)
            
        all_started = True
        for op in tx.ops:
            op_dict = {
                "type": op.op_type,
                "src": op.src,
                "dest": op.dest
            }
            if not self._execute_single_op(op_dict):
                all_started = False
        return all_started

    def _execute_single_op(self, op: dict) -> bool:
        """
        Execute an operation using FileOperations.
        Tracks the job_id for async completion tracking.
        
        Returns True if operation was queued, False on error.
        """
        if not self._file_ops:
            print("[UndoManager] No FileOperations instance connected")
            return False
            
        op_type = op.get("type")
        src = op.get("src")
        dest = op.get("dest")
        job_id = None
        
        if op_type == "rename":
            job_id = self._file_ops.rename(src, dest)
            
        elif op_type == "restore_trash":
            job_id = self._file_ops.restore_from_trash(src)
            
        elif op_type == "move":
            job_id = self._file_ops.move(src, dest)
            
        elif op_type == "copy":
            job_id = self._file_ops.copy(src, dest)
            
        elif op_type == "trash":
            job_id = self._file_ops.trash(src)
            
        elif op_type == "createFolder":
            job_id = self._file_ops.createFolder(src)
        
        if job_id:
            self._pending_job_ids.add(job_id)
            return True
        return False
    
    def _emit_availability(self):
        """Update UI about undo/redo availability."""
        self.undoAvailable.emit(self.canUndo())
        self.redoAvailable.emit(self.canRedo())
