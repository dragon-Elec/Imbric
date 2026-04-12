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

from PySide6.QtCore import QObject, Signal, Slot, QMutex, QMutexLocker
from typing import Callable, cast
from uuid import uuid4

from core.transaction import Transaction, TransactionOperation, TransactionStatus
from core.utils.path_ops import build_renamed_dest


class TransactionManager(QObject):
    # Signals
    # Emitted when a batch starts/ends
    transactionStarted = Signal(str, str)  # (tid, description)
    transactionFinished = Signal(str, str)  # (tid, status_string)

    # Emitted when progress changes (0-100)
    transactionProgress = Signal(str, int)  # (tid, percent)

    # Emitted to update UndoManager
    historyCommitted = Signal(object)  # (Transaction object)

    # Emitted when a conflict occurs, pausing the transaction
    conflictDetected = Signal(str, object)  # (job_id, conflict_data_dict)

    # Emitted when a conflict is resolved
    conflictResolved = Signal(str, str)  # (job_id, resolution_type)

    # NEW: UI-friendly batch update (description + counts)
    transactionUpdate = Signal(
        str, str, int, int
    )  # (tid, description, completed, total)

    # Granular job completion for UI reactions (select file, enter rename mode)
    # This replaces the legacy operationCompleted signal from FileOperations
    jobCompleted = Signal(str, str, str)  # (op_type, result_path, message)

    # General operation failure for UI dialogs
    operationFailed = Signal(str, str, str)  # (op_type, path, message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_transactions: dict[str, Transaction] = {}
        self._pending_conflicts: dict[
            str, dict[str, object]
        ] = {}  # job_id -> conflict_data
        self._batch_resolvers: dict[
            str, Callable
        ] = {}  # tid -> conflict_resolver callback
        self._transaction_policies: dict[str, dict] = {}  # tid -> policy dict
        self._batch_ledger: dict[
            str, list[str]
        ] = {}  # tid -> list of conflicted job_ids

        # References to subsystems (injected)
        self._file_ops = None
        self._trash_manager = None
        self._validator = None

    # -------------------------------------------------------------------------
    # PUBLIC API (Called by AppBridge / UI)
    # -------------------------------------------------------------------------

    @Slot(list, str, result=dict)
    def getTransferCapabilities(self, sources: list[str], dest: str) -> dict:
        """
        Merge capabilities of source and destination backends for UI consumption.
        Follows the 'Lowest Common Denominator' rule.
        """
        if not self._file_ops or not self._file_ops._registry:
            return {}

        registry = self._file_ops._registry

        # 1. Get Destination capabilities
        dest_backend = registry.get_io(dest)
        dest_caps = dest_backend.get_capabilities(dest)

        # 2. Get Source(s) capabilities (merge if multiple backends)
        merged_src_caps = None
        for src in sources:
            src_backend = registry.get_io(src)
            src_caps = src_backend.get_capabilities(src)

            if merged_src_caps is None:
                merged_src_caps = src_caps.copy()
            else:
                # Merge logic: if any side is slow/unreliable, the whole thing is
                if src_caps["latency_profile"] == "high":
                    merged_src_caps["latency_profile"] = "high"
                if not src_caps["reliable_mtime"]:
                    merged_src_caps["reliable_mtime"] = False
                if not src_caps["supports_preflight"]:
                    merged_src_caps["supports_preflight"] = False

        if not merged_src_caps:
            return dest_caps

        # 3. Final Merge (Source + Destination)
        final_caps = dest_caps.copy()
        if merged_src_caps["latency_profile"] == "high":
            final_caps["latency_profile"] = "high"
        if not merged_src_caps["reliable_mtime"]:
            final_caps["reliable_mtime"] = False
        if not merged_src_caps["supports_preflight"]:
            final_caps["supports_preflight"] = False

        # If any side is slow, discourage pre-flight
        if final_caps["latency_profile"] == "high":
            final_caps["supports_preflight"] = False

        return final_caps

    @Slot(str, bool, result=str)
    def startTransaction(self, description: str, is_reversible: bool = True) -> str:
        """
        Start a new batch job.
        Returns: transaction_id (str)
        """
        tid = str(uuid4())
        tx = Transaction(id=tid, description=description)
        tx.is_reversible = is_reversible
        tx.status = TransactionStatus.RUNNING

        self._active_transactions[tid] = tx

        # Notify UI a new "Job" has started
        self.transactionStarted.emit(tid, description)
        return tid

    @Slot(str, str, str, str, str)
    def addOperation(
        self, tid: str, op_type: str, src: str, dest: str = "", job_id: str = ""
    ):
        """
        Register intent to perform an operation within a transaction.
        Call this BEFORE calling file_ops.
        """
        if tid not in self._active_transactions:
            return

        tx = self._active_transactions[tid]

        # Check if we are retrying an existing operation
        # (This happens during Batch Conflict resolution)
        for op in tx.ops:
            if op.src == src and op.status == TransactionStatus.PENDING:
                op.job_id = job_id
                op.op_type = op_type
                op.dest = dest
                return

        op = TransactionOperation(op_type=op_type, src=src, dest=dest, job_id=job_id)
        tx.add_operation(op)

    @Slot(str, str, str, bool)
    def resolveConflict(
        self,
        job_id: str,
        resolution: str,
        new_name: str = "",
        apply_to_all: bool = False,
    ):
        """
        Resolve a pending conflict.

        Args:
            job_id: ID of the paused job.
            resolution: "overwrite", "rename", "skip", "cancel"
            new_name: New filename if resolution is "rename"
            apply_to_all: If True, future conflicts in this transaction use this resolution.
        """
        if not self._file_ops:
            print("[TM] CRITICAL: FileOperations not injected into TransactionManager.")
            return

        if job_id not in self._pending_conflicts:
            print(f"[TM] Warning: No pending conflict for job {job_id}")
            return

        conflict_data = self._pending_conflicts.pop(job_id)
        print(
            f"[TM] Resolving conflict {job_id} with {resolution} (apply_all={apply_to_all})"
        )

        self.conflictResolved.emit(job_id, resolution)

        # 1. Check for Deferred Resolution (Batch Job)
        # In this mode, the worker has ALREADY moved on. We need to start a NEW job for this file.
        raw_ctx = conflict_data.get("_context", {})
        if not isinstance(raw_ctx, dict):
            return

        stored_ctx = cast(dict[str, object], raw_ctx)
        tid = str(stored_ctx.get("tid", ""))
        src = str(stored_ctx.get("src", ""))
        dest = str(stored_ctx.get("dest", ""))
        op_type = str(stored_ctx.get("op_type", "copy"))

        # If it's a batch conflict, we start a fresh single-file job
        # Note: We use _file_ops.resolve_conflict first for PAUSED threads.
        # But if the thread wasn't paused, resolve_conflict will do nothing and we'll handle it here.

        # 1. Try JIT Resolution (Resume paused thread)
        is_paused = self._file_ops.resolve_conflict(
            job_id, resolution, new_name, apply_to_all
        )

        if not is_paused:
            # Thread wasn't paused, so we must execute a NEW retry operation
            if resolution == "cancel":
                # Cancel the whole transaction?
                # For now, we'll just skip this one file.
                resolution = "skip"

            if resolution == "skip":
                # Mark as skipped and increment completed_ops
                if tid in self._active_transactions:
                    tx = self._active_transactions[tid]
                    for op in tx.ops:
                        if op.src == src and op.status == TransactionStatus.PENDING:
                            op.status = TransactionStatus.COMPLETED
                            tx.completed_ops += 1
                            self.transactionUpdate.emit(
                                tid, tx.description, tx.completed_ops, tx.total_ops
                            )
                            break
                return

            print(f"[TM] Executing DEFERRED resolution for {src}")
            match resolution:
                case "overwrite":
                    if op_type == "move":
                        self._file_ops.move(
                            src, dest, transaction_id=tid, overwrite=True
                        )
                    else:
                        self._file_ops.copy(
                            src, dest, transaction_id=tid, overwrite=True
                        )
                case "rename":
                    # For rename, we usually let the UI provide a new_name or auto-rename
                    if new_name:
                        # Replace filename in dest
                        from core.utils.path_ops import build_renamed_dest

                        final_dest = build_renamed_dest(dest, new_name)
                        if op_type == "move":
                            self._file_ops.move(src, final_dest, transaction_id=tid)
                        else:
                            self._file_ops.copy(src, final_dest, transaction_id=tid)
                    else:
                        # Auto-rename
                        if op_type == "move":
                            self._file_ops.move(
                                src, dest, transaction_id=tid, overwrite=False
                            )  # Will auto-rename if implemented in move
                        else:
                            self._file_ops.copy(
                                src,
                                dest,
                                transaction_id=tid,
                                overwrite=False,
                                auto_rename=True,
                            )

    # -------------------------------------------------------------------------
    # BATCH OPERATIONS (Replaces UI-Layer Loops)
    # -------------------------------------------------------------------------

    def batchTransfer(
        self,
        sources: list[str],
        dest_dir: str,
        mode: str = "auto",
        conflict_resolver: Callable | None = None,
        policy: dict | None = None,
        skip_preflight: bool = False,
    ):
        """
        Execute a batch file transfer (paste or drag-drop).
        """
        if not self._file_ops:
            print("[TM] CRITICAL: FileOperations not injected.")
            return

        is_move = mode == "move"
        op_name = "Move" if is_move else ("Copy" if mode == "copy" else "Transfer")
        tid = self.startTransaction(f"{op_name} {len(sources)} items")

        if conflict_resolver:
            self._batch_resolvers[tid] = conflict_resolver

        if policy:
            self._transaction_policies[tid] = policy

        # JIT / Pre-flight Decision
        if skip_preflight:
            # Jump directly to execution
            batch_items = []
            for src in sources:
                job_id = str(uuid4())
                from core.utils.path_ops import build_dest_path

                dest = build_dest_path(src, dest_dir)
                op_type = mode if mode != "auto" else "move"
                self.addOperation(tid, op_type, src, dest, job_id=job_id)
                batch_items.append(
                    {
                        "job_id": job_id,
                        "src": src,
                        "dest": dest,
                        "op_type": op_type,
                        "overwrite": False,
                        "auto_rename": False,  # JIT handles it
                        "policy": policy,
                    }
                )

            self._file_ops.transfer_batch(tid, batch_items, policy=policy)
            self.commitTransaction(tid)
        else:
            # Standard Assessment
            self._file_ops.assessBatch(
                tid, sources, dest_dir, mode, resolver=conflict_resolver, policy=policy
            )

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
            self._file_ops.batchAssessmentReady.connect(self.onBatchAssessmentReady)

    def setTrashManager(self, trash_manager):
        # Legacy stub: TrashManager is now merged into FileOperations
        pass

    def setValidator(self, validator):
        """Inject OperationValidator for post-operation verification."""
        self._validator = validator

    # -------------------------------------------------------------------------
    # SIGNAL HANDLERS
    # -------------------------------------------------------------------------

    @Slot(str, list, list)
    def onBatchAssessmentReady(self, tid: str, valid_items: list, conflicts: list):
        if tid not in self._active_transactions:
            return

        resolver = self._batch_resolvers.pop(tid, None)
        policy = self._transaction_policies.pop(tid, None)

        batch_items = []

        # 1. Dispatch valid (non-conflicting) items
        for item in valid_items:
            job_id = str(uuid4())
            src = item["src"]
            dest = item["dest"]
            mode = item["mode"]
            op_type = mode if mode != "auto" else "move"

            self.addOperation(tid, op_type, src, dest, job_id=job_id)
            batch_items.append(
                {
                    "job_id": job_id,
                    "src": src,
                    "dest": dest,
                    "op_type": op_type,
                    "auto_rename": item.get("auto_rename", False),
                    "overwrite": False,
                    "policy": policy,
                }
            )

        # 2. Synchronously prompt for conflicts (safe since QDialog exec uses nested loop)
        for item in conflicts:
            src = item["src"]
            dest = item["dest"]
            mode = item["mode"]
            op_type = mode if mode != "auto" else "move"

            if resolver:
                action, final_dest = resolver(src, dest)

                if action == "cancel":
                    break
                if action == "skip":
                    continue

                dest = final_dest
                job_id = str(uuid4())
                self.addOperation(tid, op_type, src, dest, job_id=job_id)
                batch_items.append(
                    {
                        "job_id": job_id,
                        "src": src,
                        "dest": dest,
                        "op_type": op_type,
                        "overwrite": (action == "overwrite"),
                        "auto_rename": (action == "rename" and not final_dest),
                        "policy": policy,
                    }
                )
            else:
                # Default resolve strategy
                job_id = str(uuid4())
                self.addOperation(tid, op_type, src, dest, job_id=job_id)
                batch_items.append(
                    {
                        "job_id": job_id,
                        "src": src,
                        "dest": dest,
                        "op_type": op_type,
                        "overwrite": False,
                        "auto_rename": True,
                        "policy": policy,
                    }
                )

        if batch_items and self._file_ops:
            self._file_ops.transfer_batch(
                tid,
                batch_items,
                ui_refresh_rate_ms=100,
                halt_on_error=False,
                policy=policy,
            )

        self.commitTransaction(tid)

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
                    if (
                        pending_op.status == TransactionStatus.PENDING
                        and pending_op.op_type == op_type
                        and pending_op.src == path
                    ):
                        op = pending_op
                        op.job_id = job_id  # Link them!
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

    @Slot(str, str, str, str, bool, str, object)
    def onOperationFinished(
        self, tid, job_id, op_type, result_path, success, message, inverse_payload=None
    ):
        print(f"[TM] opFinished: tid={tid[:8]}, jid={job_id[:8]}, success={success}")
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
            print(
                f"[TM] WARNING: Job {job_id} not found in transaction {tid}. Possible linkage error."
            )

        if op:
            if not success and "cancel" in message.lower():
                status = TransactionStatus.CANCELLED
            elif success and op_type == "move" and "Partial Success" in message:
                status = TransactionStatus.PARTIAL
            else:
                status = (
                    TransactionStatus.COMPLETED if success else TransactionStatus.FAILED
                )

            tx.update_status(job_id, status, error=message if not success else "")

            if success:
                # [CRITICAL] Data Integrity for Undo
                op.dest = result_path
                op.result_path = result_path
                op.inverse_payload = inverse_payload
                print(f"[TM] ✓ {op_type.upper()}: {op.src} -> {result_path}")

                # [NEW] Fire async post-condition validation
                if self._validator:
                    self._validator.validate(job_id, op_type, op.src, result_path, True)
            else:
                op.error = message
                print(f"[TM] ✗ {op_type.upper()} Failed: {op.src} (Error: {message})")

        # Always increment completed_ops count regardless of success
        tx.completed_ops += 1

        # [NEW] Emit aggregated progress for UI
        percent = (
            int((tx.completed_ops / tx.total_ops) * 100) if tx.total_ops > 0 else 100
        )
        self.transactionProgress.emit(tid, percent)
        self.transactionUpdate.emit(tid, tx.description, tx.completed_ops, tx.total_ops)

        # Check if entire batch is done AND committed
        if tx.is_committed and tx.completed_ops >= tx.total_ops:
            print(f"[TM] Closing tid={tid[:8]} - all ops done")
            tx.status = TransactionStatus.COMPLETED
            self.transactionFinished.emit(tid, "Success")
            print(
                f"[TM] Transaction Completed: {tx.description} ({tx.completed_ops} ops)"
            )
            self.historyCommitted.emit(tx)
            del self._active_transactions[tid]

    @Slot(str)
    def commitTransaction(self, tid: str):
        """
        Marks a transaction as fully populated.
        If all ops are already finished (or 0 ops were added), it closes the transaction.
        """
        print(f"[TM] Commit: tid={tid[:8]}")
        if tid not in self._active_transactions:
            print(
                f"[TM] Error: tid={tid[:8]} not in active transactions: {list(self._active_transactions.keys())}"
            )
            return

        tx = self._active_transactions[tid]
        tx.is_committed = True

        # Immediate close if empty or already finished
        if tx.completed_ops >= tx.total_ops:
            tx.status = TransactionStatus.COMPLETED
            self.transactionFinished.emit(
                tid, "Success" if tx.total_ops > 0 else "Skipped"
            )
            print(
                f"[TM] Transaction Committed & Completed: {tx.description} ({tx.completed_ops} ops)"
            )
            if tx.total_ops > 0:
                self.historyCommitted.emit(tx)
            del self._active_transactions[tid]

    @Slot(str, str, str, str, str, object)
    def onOperationError(
        self,
        tid: str,
        job_id: str,
        op_type: str,
        path: str,
        message: str,
        conflict_data: object,
    ):
        """
        Handle errors and conflicts.
        """
        print(f"[TM] Error/Conflict op={op_type} path={path}: {message}")

        # Check if it is a conflict
        if conflict_data and isinstance(conflict_data, dict):
            from typing import cast

            data = cast(dict[str, object], conflict_data)
            if data.get("error") != "exists":
                self.operationFailed.emit(op_type, path, message)
                return
            # It is a conflict!
            # Store context so we know how to retry
            data["_context"] = {
                "op_type": op_type,
                "src": path,
                "dest": message,  # Fallback, likely unused if data has paths
                "tid": tid,
            }

            # Try to get paths from data directly (preferred)
            src = data.get("src_path")
            dest = data.get("dest_path")

            # Use 'path' (from signal) as source fallback if not provided in data
            if not src:
                src = path

            # [CRITICAL] Do NOT assume 'dest' = 'path' for Copy/Move operations
            # If dest is missing, we must rely on what we have or fail gracefully.
            # Restore is special: source is treated as the item to restore.

            ctx = data["_context"]
            if isinstance(ctx, dict):
                ctx["src"] = str(src) if src else path
                ctx["dest"] = str(dest) if dest else ""

            self._pending_conflicts[job_id] = data
            self.conflictDetected.emit(job_id, data)
        else:
            # Regular error
            self.operationFailed.emit(op_type, path, message)
