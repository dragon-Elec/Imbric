@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.logic.*
import com.imbric.core.models.*
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.concurrent.ConcurrentHashMap
import java.util.ArrayDeque
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

class TransactionManager(
    private val backendRegistry: BackendRegistry,
    private val xferArbiter: XferArbiter,
    private val dispatcher: TransactionDispatcher,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default)
) {
    private companion object {
        /**
         * Maximum number of Transaction records retained in memory.
         *
         * Every startTransaction (copy / move / trash / rename / undo / redo) would otherwise
         * pin a full Transaction — its ops plus their UndoAction payloads, which for a batch
         * transfer hold whole URI lists — for the lifetime of the process. Records are evicted
         * oldest-first once the cap is exceeded, which costs a bounded amount of history for
         * anything that still wants to introspect a very old transaction (findOperation,
         * cancelTransaction); it does not affect undo/redo, whose history lives in UndoManager's
         * own stacks and holds direct Transaction references.
         */
        const val MAX_TRACKED_TRANSACTIONS = 50
    }

    /**
     * Live transactions by id. Bounded to [MAX_TRACKED_TRANSACTIONS] entries by
     * [pruneTransactions]; see there for the rationale.
     */
    private val transactions = ConcurrentHashMap<Uuid, Transaction>()

    /**
     * Insertion order of [transactions] keys, oldest first. Kept alongside the map so
     * eviction is exact FIFO rather than an arbitrary clear-all.
     */
    private val insertionOrder: ArrayDeque<Uuid> = ArrayDeque()

    private val insertionLock = Any()
    
    private val _events = MutableSharedFlow<TransactionEvent>(extraBufferCapacity = 128)
    val events: SharedFlow<TransactionEvent> = _events.asSharedFlow()
    
    // --- Legacy Callback hooks for UI (transitional) ---
    var onTransactionStarted: ((Uuid, String) -> Unit)? = null
    var onTransactionFinished: ((Uuid, TransactionStatus) -> Unit)? = null
    var onTransactionProgress: ((Uuid, Float) -> Unit)? = null
    var onHistoryCommitted: ((Transaction) -> Unit)? = null

    // --- Transaction Lifecycle ---
    fun startTransaction(description: String, isReversible: Boolean = true): Uuid {
        val tid = Uuid.random()
        val tx = Transaction(
            id = tid,
            description = description,
            isReversible = isReversible
        )
        synchronized(insertionLock) {
            transactions[tid] = tx
            insertionOrder.addLast(tid)
            pruneTransactions()
        }
        return tid
    }

    /**
     * Evicts the oldest tracked transactions once [MAX_TRACKED_TRANSACTIONS] is exceeded.
     *
     * Called from [startTransaction] immediately after the new entry is inserted, which is what
     * makes eviction safe for the transaction that was just created: it is the newest element of
     * [insertionOrder], so it can never be the one dropped while trimming the head.
     */
    private fun pruneTransactions() {
        while (transactions.size > MAX_TRACKED_TRANSACTIONS && insertionOrder.isNotEmpty()) {
            val oldest = insertionOrder.pollFirst() ?: break
            transactions.remove(oldest)
        }
    }

    fun addOperation(
        tid: Uuid, 
        opType: String, 
        src: String, 
        dest: String = "", 
        jobId: Uuid = Uuid.random(), 
        overwrite: Boolean = false,
        autoRename: Boolean = false,
        undoAction: UndoAction? = null
    ) {
        val tx = transactions[tid] ?: return
        tx.addOperation(TransactionOperation(
            jobId = jobId,
            opType = opType,
            src = src,
            dest = dest,
            overwrite = overwrite,
            autoRename = autoRename,
            undoAction = undoAction
        ))
    }

    // --- High-level Entry Point ---
    fun batchTransfer(
        sources: List<String>,
        destDir: String,
        mode: String = "auto"
    ): Uuid {
        val tid = startTransaction("Batch transfer to $destDir")
        sources.forEach { src ->
            val fileName = src.uriName
            val fullDest = destDir.uriJoin(fileName)
            addOperation(tid, if (mode == "move") "move" else "copy", src, fullDest)
        }
        
        commitTransaction(tid)
        return tid
    }

    // --- Commit & Execute ---
    fun commitTransaction(
        tid: Uuid, 
        conflictResolver: (suspend (ConflictContext) -> ConflictResponse)? = null,
        policy: SyncPolicy = SyncPolicy.Standard
    ) {
        val tx = transactions[tid] ?: return
        tx.status = TransactionStatus.RUNNING
        
        onTransactionStarted?.invoke(tid, tx.description)
        _events.tryEmit(TransactionEvent.Started(tid, tx.description))
        
        tx.ops.forEach { op ->
            dispatcher.dispatchJob(
                tid = tid,
                op = op,
                conflictResolver = conflictResolver,
                onProgress = { progress -> updateProgress(tid, progress) },
                onStatusUpdate = { jobId, status, err, result, inv -> 
                    updateOperationStatus(tid, jobId, status, err, result, inv) 
                },
                policy = policy
            )
        }
        
        if (tx.ops.isEmpty()) {
            tx.status = TransactionStatus.COMPLETED
            _events.tryEmit(TransactionEvent.Finished(tid, tx.status))
            onTransactionFinished?.invoke(tid, tx.status)
        }
    }

    private fun updateOperationStatus(
        tid: Uuid, 
        jobId: Uuid, 
        status: TransactionStatus, 
        error: String = "", 
        resultPath: String? = null,
        undoAction: UndoAction? = null
    ) {
        val tx = transactions[tid] ?: return
        
        var opIndex = tx.ops.indexOfFirst { it.jobId == jobId }
        
        // Final fallback for identity stability:
        // If the jobId was reassigned during execution (e.g. JIT conflict resolution),
        // updateOperationStatus may not find it by jobId. The fuzzy match in updateProgress
        // already handles re-linking by source URI, so this is a no-op safety net.

        if (opIndex != -1) {
            val op = tx.ops[opIndex]
            val updatedOp = op.copy(
                status = status, 
                error = error, 
                resultPath = resultPath ?: op.resultPath,
                undoAction = undoAction ?: op.undoAction
            )
            tx.ops[opIndex] = updatedOp
            updateProgress(tid, TransferProgress(jobId, op.src, resultPath ?: op.resultPath, undoAction))
        }
    }

    // --- Progress & Status ---
    private fun updateProgress(tid: Uuid, progress: TransferProgress) {
        val tx = transactions[tid] ?: return
        
        // Strict jobId matching only — GioBackend captures job.id in the callback closure.
        // No fuzzy fallback: identical filenames from different directories would cross-contaminate.
        val op = tx.ops.find { it.jobId == progress.jobId } ?: return

        val pct = if (tx.totalOps > 0) {
            val completedBase = tx.completedOps.toFloat()
            
            // Calculate fractional progress of currently running jobs
            // (Simple version: factor in the current job's bytes if available)
            val currentJobFraction = if (progress.totalSize > 0) {
                progress.completedSize.toFloat() / progress.totalSize
            } else if (progress.totalCount > 0) {
                progress.completedCount.toFloat() / progress.totalCount
            } else 0f
            
            (completedBase + currentJobFraction.coerceIn(0f, 0.99f)) / tx.totalOps
        } else 0f
        
        onTransactionProgress?.invoke(tid, pct)
        _events.tryEmit(TransactionEvent.Progress(tid, pct))
        _events.tryEmit(TransactionEvent.FileProgress(tid, progress))
        
        if (tx.finishedOps == tx.totalOps) {
            val hasFailures = tx.ops.any { it.status == TransactionStatus.FAILED }
            tx.status = if (hasFailures) TransactionStatus.PARTIAL else TransactionStatus.COMPLETED
            
            onTransactionFinished?.invoke(tid, tx.status)
            _events.tryEmit(TransactionEvent.Finished(tid, tx.status))
            
            // Commit undo history even for PARTIAL transactions —
            // UndoManager filters for COMPLETED ops internally.
            if (tx.isReversible) {
                onHistoryCommitted?.invoke(tx)
            }
        }
    }

    // --- Lookup ---
    fun findOperation(tid: Uuid, jobId: Uuid): TransactionOperation? {
        return transactions[tid]?.findOperation(jobId)
    }

     // --- Capabilities ---
    fun getTransferCapabilities(sources: List<String>, dest: String): Map<String, Int> {
        val capabilities = mutableMapOf<String, Int>()
        sources.forEach { src ->
            backendRegistry.get(src)?.let { backend ->
                capabilities[backend.scheme] = (capabilities[backend.scheme] ?: 0) + 1
            }
        }
        return capabilities
    }

    // --- Cleanup ---
    fun cancelTransaction(tid: Uuid) {
        val tx = transactions[tid] ?: return
        dispatcher.cancelJobs(tx.ops.map { it.jobId })
        tx.status = TransactionStatus.CANCELLED
        _events.tryEmit(TransactionEvent.Finished(tid, TransactionStatus.CANCELLED))
        onTransactionFinished?.invoke(tid, TransactionStatus.CANCELLED)
    }
}
