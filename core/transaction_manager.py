"""
TransactionManager.py

The Central Nervous System for I/O Operations.
Orchestrates batch jobs, tracks progress, and manages Undo history.

Responsibilities:
1. Generate Transaction IDs (Batch IDs).
2. Aggregate progress from multiple single-file jobs.
3. Bundle completed jobs into single Undo entries.
4. error handling policies (Stop/Continue).
"""

from PySide6.QtCore import QObject, Signal, Slot
from typing import Dict, Optional
from uuid import uuid4
import time

from core.transaction import Transaction, TransactionOperation, TransactionStatus

class TransactionManager(QObject):
    # Signals
    # Emitted when a batch starts/ends
    transactionStarted = Signal(str, str)     # (tid, description)
    transactionFinished = Signal(str, str)    # (tid, status_string)
    
    # Emitted when progress changes (0-100)
    transactionProgress = Signal(str, int)    # (tid, percent)
    
    # Emitted to update UndoManager
    historyCommitted = Signal(object)         # (Transaction object)
    
    # Emitted when a conflict occurs, pausing the transaction
    conflictDetected = Signal(str, object)    # (job_id, conflict_data_dict)
    
    # Emitted when a conflict is resolved
    conflictResolved = Signal(str, str)       # (job_id, resolution_type)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_transactions: Dict[str, Transaction] = {}
        self._pending_conflicts: Dict[str, object] = {} # job_id -> conflict_data
        
        # References to subsystems (injected)
        self._file_ops = None
        self._trash_manager = None

    # -------------------------------------------------------------------------
    # PUBLIC API (Called by AppBridge / UI)
    # -------------------------------------------------------------------------

    @Slot(str, result=str)
    def startTransaction(self, description: str) -> str:
        """
        Start a new batch job.
        Returns: transaction_id (str)
        """
        tid = str(uuid4())
        tx = Transaction(id=tid, description=description)
        tx.status = TransactionStatus.RUNNING
        
        self._active_transactions[tid] = tx
        
        # Notify UI a new "Job" has started
        self.transactionStarted.emit(tid, description)
        return tid

    @Slot(str, str, str, str)
    def addOperation(self, tid: str, op_type: str, src: str, dest: str = ""):
        """
        Register intent to perform an operation within a transaction.
        Call this BEFORE calling file_ops.
        """
        if tid not in self._active_transactions:
            return
            
        tx = self._active_transactions[tid]
        op = TransactionOperation(op_type=op_type, src=src, dest=dest)
        tx.add_operation(op)

    @Slot(str, str, str)
    def resolveConflict(self, job_id: str, resolution: str, new_name: str = ""):
        """
        Resolve a pending conflict.
        
        Args:
            job_id: ID of the paused job.
            resolution: "overwrite", "rename", "skip", "cancel"
            new_name: New filename if resolution is "rename"
        """
        if not self._file_ops:
            print("[TM] CRITICAL: FileOperations not injected into TransactionManager.")
            return

        if job_id not in self._pending_conflicts:
            print(f"[TM] Warning: No pending conflict for job {job_id}")
            return
            
        conflict_data = self._pending_conflicts.pop(job_id)
        print(f"[TM] Resolving conflict {job_id} with {resolution}")
        
        self.conflictResolved.emit(job_id, resolution)
        
        # Re-execute the operation based on resolution
        # We need to know WHAT the operation was. 
        # conflict_data usually has 'op_type', 'src', 'dest' (implied)
        # But conflict_data from FileOps is structured: {error, src{}, dest{}}
        # It doesn't have op_type/src/dest paths!
        # Wait, the signal emitted (job_id, op_type, path, message, data).
        # We need to store op_type and path when we catch the error!
        
        stored_ctx = conflict_data.get("_context", {})
        op_type = stored_ctx.get("op_type")
        src = stored_ctx.get("src")
        dest = stored_ctx.get("dest")
        
        if not op_type or not src:
            print(f"[TM] Error: Missing context for conflict {job_id}")
            return

        tid = stored_ctx.get("tid") # Extract TID from context to use in resolution calls
        if not tid:
             print(f"[TM] Warning: No TID found in conflict context for {job_id}")
             # try to find it via job_id?
             pass

        # Execute Resolution
        if resolution == "overwrite":
            # Re-submit with overwrite enabled
            
            if op_type == "restore":
                if self._file_ops:
                    self._file_ops.restore(src, transaction_id=tid, overwrite=True)
            elif op_type == "copy":
                if self._file_ops:
                    print(f"[TM] Resolving COPY conflict with overwrite=True")
                    self._file_ops.copy(src, dest, transaction_id=tid, overwrite=True)
            elif op_type == "move":
                if self._file_ops:
                    print(f"[TM] Resolving MOVE conflict with overwrite=True")
                    self._file_ops.move(src, dest, transaction_id=tid, overwrite=True)
                 
        elif resolution == "rename":
            # Calculate new destination
            import os
            base_dir = os.path.dirname(dest)
            new_dest = os.path.join(base_dir, new_name) if new_name else dest
            
            if op_type == "restore":
                if self._file_ops:
                    self._file_ops.restore(src, transaction_id=tid, rename_to=new_name)
            elif op_type == "copy":
                if self._file_ops:
                    self._file_ops.copy(src, new_dest, transaction_id=tid)
            elif op_type == "move":
                if self._file_ops:
                    self._file_ops.move(src, new_dest, transaction_id=tid)

    # -------------------------------------------------------------------------
    # DEPENDENCY INJECTION
    # -------------------------------------------------------------------------
    
    def setFileOperations(self, file_ops):
        self._file_ops = file_ops
        # Connect signals
        if self._file_ops:
            self._file_ops.operationStarted.connect(self.onOperationStarted)
            self._file_ops.operationFinished.connect(self.onOperationFinished)
            self._file_ops.operationProgress.connect(self.onOperationProgress)
            self._file_ops.operationError.connect(self.onOperationError)
        
    def setTrashManager(self, trash_manager):
        # Legacy stub: TrashManager is now merged into FileOperations
        pass

    # -------------------------------------------------------------------------
    # SIGNAL HANDLERS
    # -------------------------------------------------------------------------
    
    @Slot(str, str, str)
    def onOperationStarted(self, job_id, op_type, path):
        # Find which transaction this belongs to
        for tid, tx in self._active_transactions.items():
            # 1. Try exact match (if manually assigned)
            op = tx.find_operation(job_id)
            
            # 2. If not found, look for a matching PENDING operation
            if not op:
                for pending_op in tx.ops:
                    # Match if pending AND op_type matches AND source matches
                    if (pending_op.status == TransactionStatus.PENDING and 
                        pending_op.op_type == op_type and 
                        pending_op.src == path):
                        op = pending_op
                        op.job_id = job_id # Link them!
                        break
            
            if op:
                tx.update_status(job_id, TransactionStatus.RUNNING)
                return

    @Slot(str, int, int)
    def onOperationProgress(self, job_id, current, total):
        for tid, tx in self._active_transactions.items():
            op = tx.find_operation(job_id)
            if op:
                # Calculate total transaction progress
                # Simple average for now
                if total > 0:
                    percent = int((current / total) * 100)
                    # Ideally we aggregate all ops, but simplified for now:
                    self.transactionProgress.emit(tid, percent)
                return

    @Slot(str, str, str, str, bool, str)
    def onOperationFinished(self, tid, job_id, op_type, result_path, success, message):
        if tid not in self._active_transactions:
            return

        tx = self._active_transactions[tid]
        op = tx.find_operation(job_id)
        
        if op:
            status = TransactionStatus.COMPLETED if success else TransactionStatus.FAILED
            tx.update_status(job_id, status, error=message if not success else "")
            
            if success:
                tx.completed_ops += 1
                op.dest = result_path # Update result path
        
        # Check if entire batch is done
        if tx.completed_ops >= tx.total_ops:
            tx.status = TransactionStatus.COMPLETED
            self.transactionFinished.emit(tid, "Success")
            self.historyCommitted.emit(tx)
            del self._active_transactions[tid]
        elif not success:
            # Policy: Continue or Stop? 
            pass

    @Slot(str, str, str, str, str, object)
    def onOperationError(self, tid: str, job_id: str, op_type: str, path: str, message: str, conflict_data: object):
        """
        Handle errors and conflicts.
        """
        print(f"[TM] Error/Conflict op={op_type} path={path}: {message}")
        
        # Check if it is a conflict
        if conflict_data and isinstance(conflict_data, dict) and conflict_data.get("error") == "exists":
            # It is a conflict!
            # Store context so we know how to retry
            conflict_data["_context"] = {
                "op_type": op_type,
                "src": path, 
                "dest": message, # Fallback, likely unused if conflict_data has paths
                "tid": tid
            }
            
            # Try to get paths from conflict_data directly (preferred)
            src = conflict_data.get("src_path", "")
            dest = conflict_data.get("dest_path", "")
            
            # Fallback logic if paths are missing from data
            if not src and op_type == "restore":
                src = path
            if not dest and op_type != "restore":
                dest = path
                
            conflict_data["_context"]["src"] = src
            conflict_data["_context"]["dest"] = dest
            
            self._pending_conflicts[job_id] = conflict_data
            self.conflictDetected.emit(job_id, conflict_data)
        else:
             # Regular error
             pass
