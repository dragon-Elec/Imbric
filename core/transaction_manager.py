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
from typing import Dict, List, Optional, Callable, Tuple
from uuid import uuid4

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
    
    # NEW: UI-friendly batch update (description + counts)
    transactionUpdate = Signal(str, str, int, int)  # (tid, description, completed, total)
    
    # Granular job completion for UI reactions (select file, enter rename mode)
    # This replaces the legacy operationCompleted signal from FileOperations
    jobCompleted = Signal(str, str, str)  # (op_type, result_path, message)

    # General operation failure for UI dialogs
    operationFailed = Signal(str, str, str) # (op_type, path, message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_transactions: Dict[str, Transaction] = {}
        self._pending_conflicts: Dict[str, object] = {} # job_id -> conflict_data
        
        # References to subsystems (injected)
        self._file_ops = None
        self._trash_manager = None
        self._validator = None

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

    @Slot(str, str, str, str, str)
    def addOperation(self, tid: str, op_type: str, src: str, dest: str = "", job_id: str = ""):
        """
        Register intent to perform an operation within a transaction.
        Call this BEFORE calling file_ops.
        """
        if tid not in self._active_transactions:
            return
            
        tx = self._active_transactions[tid]
        op = TransactionOperation(op_type=op_type, src=src, dest=dest, job_id=job_id)
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
        
        stored_ctx = conflict_data.get("_context", {})
        op_type = stored_ctx.get("op_type")
        src = stored_ctx.get("src")
        dest = stored_ctx.get("dest")
        
        if not op_type or not src:
            print(f"[TM] Error: Missing context for conflict {job_id}")
            return

        tid = stored_ctx.get("tid")
        if not tid:
             print(f"[TM] Warning: No TID found in conflict context for {job_id}")

        # Execute Resolution
        if resolution == "overwrite":
            if op_type == "restore":
                self._file_ops.restore(src, transaction_id=tid, overwrite=True)
            elif op_type == "copy":
                print(f"[TM] Resolving COPY conflict with overwrite=True")
                self._file_ops.copy(src, dest, transaction_id=tid, overwrite=True)
            elif op_type == "move":
                print(f"[TM] Resolving MOVE conflict with overwrite=True")
                self._file_ops.move(src, dest, transaction_id=tid, overwrite=True)
                 
        elif resolution == "rename":
            new_dest = self._file_ops.build_renamed_dest(dest, new_name) if dest else dest
            
            if op_type == "restore":
                self._file_ops.restore(src, transaction_id=tid, rename_to=new_name)
            elif op_type == "copy":
                self._file_ops.copy(src, new_dest, transaction_id=tid)
            elif op_type == "move":
                self._file_ops.move(src, new_dest, transaction_id=tid)

    # -------------------------------------------------------------------------
    # BATCH OPERATIONS (Replaces UI-Layer Loops)
    # -------------------------------------------------------------------------

    def batchTransfer(
        self,
        sources: List[str],
        dest_dir: str,
        mode: str = "auto",
        conflict_resolver: Optional[Callable] = None,
    ):
        """
        Execute a batch file transfer (paste or drag-drop).

        This replaces the synchronous loop that was previously in FileManager.
        Core now owns the iteration logic, same-folder detection, and conflict
        resolution orchestration.

        Args:
            sources: List of source paths/URIs.
            dest_dir: Destination directory path/URI.
            mode: "copy", "move", or "auto".
            conflict_resolver: Optional callback(src, dest) -> (action, final_dest).
                               Returns a tuple of (action_string, final_dest).
                               action_string is one of: "cancel", "skip", "overwrite", "rename".
                               If None, auto-rename is used for conflicts.
        """
        if not self._file_ops:
            print("[TM] CRITICAL: FileOperations not injected.")
            return

        is_move = mode == "move"
        op_name = "Move" if is_move else ("Copy" if mode == "copy" else "Transfer")
        tid = self.startTransaction(f"{op_name} {len(sources)} items")

        for src in sources:
            if not self._file_ops.check_exists(src):
                continue

            # Let FileOperations build the actual dest path.
            # We only need to know same-folder for the skip/duplicate decision.
            dest = self._file_ops.build_dest_path(src, dest_dir)

            # Same-folder detection
            if self._file_ops.is_same_file(src, dest):
                if is_move:
                    continue  # Can't move a file to itself
                else:
                    # Same-folder copy = Duplicate with auto-rename
                    self._file_ops.copy(src, dest, transaction_id=tid, auto_rename=True)
                    continue

            # Conflict resolution
            if conflict_resolver:
                action, final_dest = conflict_resolver(src, dest)

                if action == "cancel":
                    break
                if action == "skip":
                    continue
                dest = final_dest

            self._file_ops.transfer(src, dest, mode=mode, transaction_id=tid)

        self.commitTransaction(tid)

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

    def setValidator(self, validator):
        """Inject OperationValidator for post-operation verification."""
        self._validator = validator

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
        # [FIX] Always emit jobCompleted for UI, even for orphan jobs (no transaction)
        # This provides granular feedback for Smart UI behaviors (select after rename, etc.)
        if success:
            self.jobCompleted.emit(op_type, result_path, message)
        
        if tid not in self._active_transactions:
            return

        tx = self._active_transactions[tid]
        op = tx.find_operation(job_id)
        
        # [STRICT MODE] No fuzzy matching - ID must be correct
        if not op:
            print(f"[TM] WARNING: Job {job_id} not found in transaction {tid}. Possible linkage error.")

        if op:
            status = TransactionStatus.COMPLETED if success else TransactionStatus.FAILED
            tx.update_status(job_id, status, error=message if not success else "")
            
            if success:
                # [CRITICAL] Data Integrity for Undo
                # For Copy/Move/Rename: result_path is the final destination (e.g. "file (2).txt")
                # For Trash: result_path is the source (item trashed) - handled by default logic
                op.dest = result_path 
                op.result_path = result_path
                print(f"[TM] ✓ {op_type.upper()}: {op.src} -> {result_path}")
                
                # [NEW] Fire async post-condition validation
                if self._validator:
                    self._validator.validate(job_id, op_type, op.src, result_path, True)
            else:
                 op.error = message
                 print(f"[TM] ✗ {op_type.upper()} Failed: {op.src} (Error: {message})")
        
        # Always increment completed_ops count regardless of success
        # This prevents "hanging" transactions if one item fails
        tx.completed_ops += 1
        
        # [NEW] Emit aggregated progress for UI
        percent = int((tx.completed_ops / tx.total_ops) * 100) if tx.total_ops > 0 else 100
        self.transactionProgress.emit(tid, percent)
        self.transactionUpdate.emit(tid, tx.description, tx.completed_ops, tx.total_ops)

        # Check if entire batch is done AND committed
        if tx.is_committed and tx.completed_ops >= tx.total_ops:
            tx.status = TransactionStatus.COMPLETED
            self.transactionFinished.emit(tid, "Success")
            print(f"[TM] Transaction Completed: {tx.description} ({tx.completed_ops} ops)")
            self.historyCommitted.emit(tx)
            del self._active_transactions[tid]

    @Slot(str)
    def commitTransaction(self, tid: str):
        """
        Marks a transaction as fully populated.
        If all ops are already finished (or 0 ops were added), it closes the transaction.
        """
        if tid not in self._active_transactions:
            return
            
        tx = self._active_transactions[tid]
        tx.is_committed = True
        
        # Immediate close if empty or already finished
        if tx.completed_ops >= tx.total_ops:
            tx.status = TransactionStatus.COMPLETED
            self.transactionFinished.emit(tid, "Success" if tx.total_ops > 0 else "Skipped")
            print(f"[TM] Transaction Committed & Completed: {tx.description} ({tx.completed_ops} ops)")
            if tx.total_ops > 0:
                self.historyCommitted.emit(tx)
            del self._active_transactions[tid]

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
            src = conflict_data.get("src_path")
            dest = conflict_data.get("dest_path")
            
            # Use 'path' (from signal) as source fallback if not provided in data
            if not src:
                src = path
            
            # [CRITICAL] Do NOT assume 'dest' = 'path' for Copy/Move operations
            # If dest is missing, we must rely on what we have or fail gracefully.
            # Restore is special: source is treated as the item to restore.
            
            conflict_data["_context"]["src"] = src
            conflict_data["_context"]["dest"] = dest
            
            self._pending_conflicts[job_id] = conflict_data
            self.conflictDetected.emit(job_id, conflict_data)
        else:
            # Regular error
            self.operationFailed.emit(op_type, path, message)
