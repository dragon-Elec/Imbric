"""
UndoManager.py

Handles application-wide Undo/Redo stack.
Listens to TransactionManager for committed history.
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import List, Optional, Set
from core.transaction import Transaction, TransactionStatus
from collections import deque
from enum import Enum

class PendingMode(Enum):
    NONE = 0
    UNDO = 1
    REDO = 2

class UndoManager(QObject):
    # Signals
    stackChanged = Signal(bool, bool) # (can_undo, can_redo)
    undoTriggered = Signal(str)       # (description)
    redoTriggered = Signal(str)
    
    # New Signals for Async Reliability
    operationFinished = Signal(bool, str) # success, message (for UI feedback)
    busyChanged = Signal(bool)

    def __init__(self, transaction_manager, parent=None):
        super().__init__(parent)
        self.tm = transaction_manager
        
        # Stacks
        self._undo_stack: deque[Transaction] = deque(maxlen=50)
        self._redo_stack: deque[Transaction] = deque(maxlen=50)
        
        # Async State
        self._pending_mode = PendingMode.NONE
        self._pending_tx: Optional[Transaction] = None
        self._pending_job_ids: Set[str] = set()
        self._pending_errors: List[str] = []
        
        # Connect
        self.tm.historyCommitted.connect(self._on_history_committed)
        
        # Dependency Injection
        self._file_ops = None

    def setFileOperations(self, file_ops):
        if self._file_ops:
            try:
                self._file_ops.operationFinished.disconnect(self._on_op_finished)
                self._file_ops.operationError.disconnect(self._on_op_error)
            except: pass
            
        self._file_ops = file_ops
        
        if self._file_ops:
            self._file_ops.operationFinished.connect(self._on_op_finished)
            self._file_ops.operationError.connect(self._on_op_error)

    @Slot(object)
    def _on_history_committed(self, tx: Transaction):
        # Ignore history events caused by our own undo/redo actions
        if self._pending_mode != PendingMode.NONE:
            return

        self._undo_stack.append(tx)
        self._redo_stack.clear()
        self._emit_status()

    def can_undo(self): 
        return len(self._undo_stack) > 0 and self._pending_mode == PendingMode.NONE
        
    def can_redo(self): 
        return len(self._redo_stack) > 0 and self._pending_mode == PendingMode.NONE

    @Slot()
    def undo(self):
        if not self.can_undo(): return
        
        tx = self._undo_stack.pop()
        
        print(f"[Undo] Reversing '{tx.description}'")
        
        # Enter Busy State
        self._pending_mode = PendingMode.UNDO
        self._pending_tx = tx
        self._pending_job_ids.clear()
        self._pending_errors.clear()
        self.busyChanged.emit(True)
        self._emit_status() # Disable buttons
        
        # Execute
        self.undoTriggered.emit(tx.description)
        self._perform_inversion(tx, is_undo=True)
        
        # Check if immediate complete (sync ops or no ops)
        if not self._pending_job_ids:
            self._finalize_pending(success=True)

    @Slot()
    def redo(self):
        if not self.can_redo(): return
        
        tx = self._redo_stack.pop()
        
        print(f"[Redo] Re-applying '{tx.description}'")
        
        # Enter Busy State
        self._pending_mode = PendingMode.REDO
        self._pending_tx = tx
        self._pending_job_ids.clear()
        self._pending_errors.clear()
        self.busyChanged.emit(True)
        self._emit_status()
        
        # Execute
        self.redoTriggered.emit(tx.description)
        self._perform_inversion(tx, is_undo=False)
        
        if not self._pending_job_ids:
            self._finalize_pending(success=True)

    def _emit_status(self):
        self.stackChanged.emit(self.can_undo(), self.can_redo())
        
    def _perform_inversion(self, tx: Transaction, is_undo: bool):
        if not self._file_ops: return
        
        ops = reversed(tx.ops) if is_undo else tx.ops
        
        for op in ops:
            # Determine inverse action for UNDO, or normal action for REDO
            # We map this to FileOperations calls which return job_ids
            jid = None
            
            # Extract common data
            src = op.src
            dest = op.dest or op.result_path # Fallback to result if dest was empty (e.g. createFolder)
            
            if is_undo:
                # INVERSE LOGIC
                if op.op_type == "createFolder":
                    # Undo Create -> Trash the *actual* created path (result_path)
                    # If result_path is missing (legacy), fall back to src
                    target_to_trash = op.result_path if op.result_path else src
                    jid = self._file_ops.trash(target_to_trash)
                    
                elif op.op_type == "trash":
                    # Undo Trash -> Restore
                    # Restore logic handles collisions internally or via conflict dialog
                    jid = self._file_ops.restore_from_trash(src)
                    
                elif op.op_type == "rename":
                    # Undo Rename (A->B) -> Rename (B->A)
                    # src=A, dest=B. Inverse: src=B, dest=basename(A)
                    # We use result_path as the most accurate 'current' location of B
                    current_path = op.result_path if op.result_path else dest
                    if current_path and src:
                        original_name = src.split('/')[-1]
                        jid = self._file_ops.rename(current_path, original_name)
                        
                elif op.op_type == "copy":
                    # Undo Copy -> Trash the copy
                    target = op.result_path if op.result_path else dest
                    
                    # [SAFETY] If target is same as source (duplication) and result_path missed,
                    # we risk deleting the source. Abort if strictly identical.
                    if target and target == src and not op.result_path:
                         print(f"[UndoManager] Critical Safety: Skipping undo of {op.op_type} because result_path is missing and dest==src.")
                         continue

                    if target:
                        jid = self._file_ops.trash(target)
                        
                elif op.op_type == "move":
                    # Undo Move (A->B) -> Move (B->A)
                    # This relies on file_ops.move handling 'src' as a full target path
                    current_loc = op.result_path if op.result_path else dest
                    if current_loc and src:
                        jid = self._file_ops.move(current_loc, src)
            else:
                # REDO LOGIC (Standard Replay)
                if op.op_type == "createFolder":
                    jid = self._file_ops.createFolder(src)
                elif op.op_type == "trash":
                    jid = self._file_ops.trash(src)
                elif op.op_type == "restore_trash": # (If we had this op type)
                    jid = self._file_ops.restore_from_trash(src)
                elif op.op_type == "rename":
                    # Rename src -> dest_name
                     if dest:
                         new_name = dest.split('/')[-1]
                         jid = self._file_ops.rename(src, new_name)
                elif op.op_type == "copy":
                    jid = self._file_ops.copy(src, dest)
                elif op.op_type == "move":
                    jid = self._file_ops.move(src, dest)
            
            if jid:
                self._pending_job_ids.add(jid)

    # --- ASYNC HANDLERS ---
    
    @Slot(str, str, str, str, bool, str)
    def _on_op_finished(self, tid, job_id, op_type, path, success, msg):
        if job_id in self._pending_job_ids:
            self._pending_job_ids.discard(job_id)
            if not success:
                self._pending_errors.append(msg)
            
            if not self._pending_job_ids:
                # All done
                final_success = len(self._pending_errors) == 0
                self._finalize_pending(final_success)

    @Slot(str, str, str, str, str, object)
    def _on_op_error(self, tid, job_id, op_type, path, msg, conflict):
        if job_id in self._pending_job_ids:
            # We treat error signal as a completion of that specific job (failed)
            # The finished signal usually follows error? 
            # In file_workers.py: emit_finished is called after operationError.
            # So we rely on _on_op_finished to handle the decrement.
            pass

    def _finalize_pending(self, success: bool):
        tx = self._pending_tx
        mode = self._pending_mode
        errs = self._pending_errors
        
        # Reset State
        self._pending_mode = PendingMode.NONE
        self._pending_tx = None
        self._pending_job_ids.clear()
        self._pending_errors = []
        self.busyChanged.emit(False)
        
        # Update Stacks based on outcome
        if mode == PendingMode.UNDO:
            if success:
                self._redo_stack.append(tx)
                print(f"[UndoManager] Undo Complete: {tx.description}")
                self.operationFinished.emit(True, f"Undid: {tx.description}")
            else:
                # Execution failed. Revert stack state? 
                # Ideally we keep it in Undo stack because it wasn't successfully undone.
                self._undo_stack.append(tx) 
                print(f"[UndoManager] Undo Failed: {errs}")
                error_msg = errs[0] if errs else "Unknown error"
                self.operationFinished.emit(False, f"Undo failed: {error_msg}")
                
        elif mode == PendingMode.REDO:
            if success:
                self._undo_stack.append(tx)
                print(f"[UndoManager] Redo Complete: {tx.description}")
                self.operationFinished.emit(True, f"Redid: {tx.description}")
            else:
                # Execution failed. Keep in Redo stack?
                self._redo_stack.append(tx)
                print(f"[UndoManager] Redo Failed: {errs}")
                error_msg = errs[0] if errs else "Unknown error"
                self.operationFinished.emit(False, f"Redo failed: {error_msg}")

        self._emit_status()
