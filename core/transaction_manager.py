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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_transactions: Dict[str, Transaction] = {}
        # We need a reference to undo_manager to push history? 
        # Or better: emit a signal 'historyCommitted' and let UndoManager connect to it.
        # Decoupling is better.

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

    # -------------------------------------------------------------------------
    # SIGNAL HANDLERS (Connected to FileOperations)
    # -------------------------------------------------------------------------

    @Slot(str, str, str)
    def onOperationStarted(self, job_id: str, op_type: str, path: str):
        """
        Legacy/Direct handler. Use onTransactionOperationStarted if possible.
        For now, FileOps doesn't pass TID in signals yet. 
        We need to modify FileOps to include TID in its signals.
        """
        pass 

    @Slot(str, str, str, str, bool, str)
    def onOperationFinished(self, tid: str, job_id: str, op_type: str, result_path: str, success: bool, message: str):
        """
        Called when a single file op finishes.
        We update the batch progress.
        """
        if tid not in self._active_transactions:
            return

        tx = self._active_transactions[tid]
        
        # Find the matching operation (simple FIFO or match by src?)
        # Since we added them in order, and we might not have job_id mapped yet 
        # (unless we return job_id from addOperation).
        # For simplicity in this step, we just increment counter. 
        # Ideally, we map job_ids.

        if success:
            tx.completed_ops += 1
            # Update the specific op status if we can find it.
            # (Skipping strict mapping for now to keep it simple)
            
            # Update Progress
            percent = int(tx.get_progress() * 100)
            self.transactionProgress.emit(tid, percent)
            
        else:
            # Handle Failure
            tx.error_message = message
            # Policy: Do we fail the whole batch? Or continue?
            # For now: Log it and continue.
            pass

        # Check if Batch is Done
        if tx.completed_ops >= tx.total_ops: # Simplified completion check
            self._commit_transaction(tid)

    def _commit_transaction(self, tid: str):
        """Finalize the transaction and push to history."""
        if tid not in self._active_transactions:
            return
            
        tx = self._active_transactions[tid]
        tx.status = TransactionStatus.COMPLETED
        
        self.transactionFinished.emit(tid, "completed")
        self.historyCommitted.emit(tx)
        
        # Cleanup
        del self._active_transactions[tid]
