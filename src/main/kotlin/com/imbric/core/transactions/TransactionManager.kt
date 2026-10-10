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
     * Evicts the oldest *finished* tracked transactions once [MAX_TRACKED_TRANSACTIONS]
     * is exceeded.
     *
     * Called from [startTransaction] immediately after the new entry is inserted, which is what
     * makes eviction safe for the transaction that was just created: it is the newest element of
     * [insertionOrder], so it can never be the one dropped while trimming the head.
     *
     * PENDING/RUNNING transactions are skipped and re-queued: a live tx can sit in a
     * seconds-wide planning window (TransferOrchestrator suspends in metadata I/O between
     * startTransaction and commitTransaction). Evicting one there makes addOperation and
     * commitTransaction silent no-ops, and the transaction's Finished event never fires at
     * all — a permanent park. If every tracked tx is live, the ring legitimately exceeds the
     * cap by the in-flight count and the next prune trims again.
     */
    private fun pruneTransactions() {
        while (transactions.size > MAX_TRACKED_TRANSACTIONS) {
            var evictedAny = false
            val ringSize = insertionOrder.size
            repeat(ringSize) {
                val tid = insertionOrder.pollFirst() ?: return@repeat
                val tx = transactions[tid]
                val live = tx != null &&
                    (tx.status == TransactionStatus.PENDING || tx.status == TransactionStatus.RUNNING)
                if (live) {
                    insertionOrder.addLast(tid) // keep it in the ring for a later prune pass
                } else {
                    transactions.remove(tid)
                    evictedAny = true
                }
            }
            if (!evictedAny) return
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
        val op = TransactionOperation(
            jobId = jobId,
            opType = opType,
            src = src,
            dest = dest,
            overwrite = overwrite,
            autoRename = autoRename,
            undoAction = undoAction
        )
        // Same monitor as updateOperationStatus / updateProgress: ops is a plain ArrayList and
        // readers iterate it while workers write slots.
        synchronized(tx) { tx.addOperation(op) }
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

        // Iterate a snapshot, not the live list: from the first dispatchJob onwards, worker
        // threads are already writing tx.ops slots as this loop runs.
        val opsSnapshot: List<TransactionOperation> = synchronized(tx) {
            // Never resurrect a CANCELLED tx: a cancel issued during the (seconds-wide)
            // planning window already emitted Finished once; flipping back to RUNNING would
            // emit a second terminal for one tid when the workers finish.
            if (tx.status == TransactionStatus.CANCELLED) return
            tx.status = TransactionStatus.RUNNING
            tx.ops.toList()
        }
        
        onTransactionStarted?.invoke(tid, tx.description)
        _events.tryEmit(TransactionEvent.Started(tid, tx.description))
        
        opsSnapshot.forEach { op ->
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
        
        if (opsSnapshot.isEmpty()) {
            val emptyStatus = synchronized(tx) {
                tx.status = TransactionStatus.COMPLETED
                tx.status
            }
            emitTerminal(TransactionEvent.Finished(tid, emptyStatus))
            onTransactionFinished?.invoke(tid, emptyStatus)
        }
    }

    /**
     * Terminal events must not be lossy. Progress events stay best-effort `tryEmit`, but a
     * dropped `Finished` parks every waiter forever (the orchestrator's collector.join(),
     * undo/redo's `.first()`) — status reachability is worthless if delivery isn't. The
     * SharedFlow is replay-0 with a 128-slot buffer shared across ALL transactions, so a
     * stalled subscriber can make `tryEmit` fail with false, which the old code ignored.
     * A suspending `emit` waits for the subscribers instead of dropping. Fast path first:
     * when the buffer has room the terminal lands synchronously with no coroutine at all;
     * the suspending fallback covers the stalled-subscriber case. If the manager scope is
     * itself cancelled (teardown racing a finisher), the launch no-ops and the event is
     * lost — accepted: buffer-full plus a dead scope means no waiter is left to collect.
     */
    private fun emitTerminal(event: TransactionEvent) {
        if (_events.tryEmit(event)) return
        scope.launch { _events.emit(event) }
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

        // Final fallback for identity stability:
        // If the jobId was reassigned during execution (e.g. JIT conflict resolution),
        // updateOperationStatus may not find it by jobId. The fuzzy match in updateProgress
        // already handles re-linking by source URI, so this is a no-op safety net.
        var src: String? = null
        var effectiveResult: String? = null
        synchronized(tx) {
            val opIndex = tx.ops.indexOfFirst { it.jobId == jobId }
            if (opIndex != -1) {
                // Read-modify-write under the tx monitor. Without it, two workers updating
                // different slots of the same ArrayList can interleave the read and the write
                // and lose one of the two status updates — which would strand the transaction
                // short of finishedOps == totalOps forever.
                val op = tx.ops[opIndex]
                val merged = op.copy(
                    status = status, 
                    error = error, 
                    resultPath = resultPath ?: op.resultPath,
                    undoAction = undoAction ?: op.undoAction
                )
                tx.ops[opIndex] = merged
                src = merged.src
                effectiveResult = merged.resultPath
            }
        }
        val opSrc = src ?: return

        // Deliberately outside the synchronized block above: re-entering updateProgress is safe
        // (the monitor is reentrant), but holding it across the progress callbacks would serialize
        // every worker's UI notification.
        updateProgress(tid, TransferProgress(jobId, opSrc, effectiveResult, undoAction))
    }

    // --- Progress & Status ---
    private fun updateProgress(tid: Uuid, progress: TransferProgress) {
        val tx = transactions[tid] ?: return

        // 🔒 One critical section per transaction, held only long enough to *derive* state:
        // the op lookup, the percentage computed from tx.completedOps, and the
        // finishedOps == totalOps completion test all have to read one consistent snapshot of
        // tx.ops. They used to be unsynchronized, so concurrent workers could observe a torn
        // state — a stale non-terminal slot that made the completion test miss, or fire it twice.
        // The status counters are recomputed (Transaction.finishedOps iterates ops) rather than
        // incremented, so there is no separate counter to keep in step; the invariant that matters
        // is "this write and the read that decides Finished are mutually exclusive".
        var pct = 0f
        var finalStatus: TransactionStatus? = null
        synchronized(tx) {
            // Strict jobId matching only — GioBackend captures job.id in the callback closure.
            // No fuzzy fallback: identical filenames from different directories would cross-contaminate.
            if (tx.ops.none { it.jobId == progress.jobId }) return

            pct = if (tx.totalOps > 0) {
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

            // tx.status as the "not yet finished" latch: commitTransaction sets RUNNING before
            // dispatching, so a RUNNING tx that has finished every op is exactly the terminal
            // transition — and once we flip it here, no sibling worker can emit a second Finished.
            if (tx.status == TransactionStatus.RUNNING && tx.finishedOps == tx.totalOps) {
                val hasFailures = tx.ops.any {
                    it.status == TransactionStatus.FAILED || it.status == TransactionStatus.CANCELLED
                }
                val resolved = if (hasFailures) TransactionStatus.PARTIAL else TransactionStatus.COMPLETED
                finalStatus = resolved
                tx.status = resolved
            }
        }
        
        onTransactionProgress?.invoke(tid, pct)
        _events.tryEmit(TransactionEvent.Progress(tid, pct))
        _events.tryEmit(TransactionEvent.FileProgress(tid, progress))

        // Emitted outside the monitor so the 31 sibling workers are never blocked on a UI callback.
        val terminal = finalStatus ?: return
        onTransactionFinished?.invoke(tid, terminal)
        emitTerminal(TransactionEvent.Finished(tid, terminal))
        
        // Commit undo history even for PARTIAL transactions —
        // UndoManager filters for COMPLETED ops internally.
        if (tx.isReversible) {
            onHistoryCommitted?.invoke(tx)
        }
    }

    // --- Lookup ---
    /**
     * Per-op lookup for callers outside the dispatch lifecycle (UndoManager's redo capture).
     * Locked like the writers: [Transaction.findOperation] iterates the live `ops` list
     * while workers mutate it.
     */
    fun findOperation(tid: Uuid, jobId: Uuid): TransactionOperation? {
        val tx = transactions[tid] ?: return null
        return synchronized(tx) { tx.findOperation(jobId) }
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
        val alreadyTerminal = synchronized(tx) {
            if (tx.status != TransactionStatus.PENDING && tx.status != TransactionStatus.RUNNING) {
                // A worker already flipped this tx terminal — emitting CANCELLED now would be
                // a second Finished for one tx (COMPLETED then CANCELLED reaching the UI).
                true
            } else {
                tx.status = TransactionStatus.CANCELLED
                false
            }
        }
        if (alreadyTerminal) return
        val jobIds = synchronized(tx) { tx.ops.map { it.jobId } }
        dispatcher.cancelJobs(jobIds)
        emitTerminal(TransactionEvent.Finished(tid, TransactionStatus.CANCELLED))
        onTransactionFinished?.invoke(tid, TransactionStatus.CANCELLED)
    }
}
