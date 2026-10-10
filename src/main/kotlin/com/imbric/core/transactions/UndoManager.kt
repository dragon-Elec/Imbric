@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.models.FileJob
import com.imbric.core.models.UndoAction
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi
import java.util.Deque
import java.util.ArrayDeque

/**
 * Stack-based undo/redo for transactions.
 * Dispatches typed UndoAction variants to the correct reversal logic.
 */
class UndoManager(
    private val backendRegistry: BackendRegistry,
    private val transactionManager: TransactionManager,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default)
) {
    private companion object {
        /**
         * Upper bound on entries kept per history stack. A Transaction retains its operations
         * and their UndoAction payloads (which can be large: whole URI lists for a batch
         * transfer), so an unbounded stack is a slow leak on a long-lived session. When the
         * cap is hit the oldest entries are discarded, which only loses undo/redo depth —
         * it never corrupts state, since a Transaction here is only ever read.
         */
        const val MAX_STACK_SIZE = 100

        /**
         * Failsafe for the undo/redo Finished-event wait. A well-behaved transaction always
         * emits Finished; this bounds the wait so a lost event degrades into "push the
         * transaction back onto its stack" instead of parking the coroutine forever with
         * `busy` held true, which would disable undo/redo permanently.
         */
        const val UNDO_TIMEOUT_MS = 60_000L
    }

    private val undoStack: Deque<Transaction> = ArrayDeque()
    private val redoStack: Deque<Transaction> = ArrayDeque()
    private val busy = java.util.concurrent.atomic.AtomicBoolean(false)

    // --- Callbacks for UI ---
    var onStackChanged: ((Boolean, Boolean) -> Unit)? = null
    var onBusyChanged: ((Boolean) -> Unit)? = null

    fun attach() {
        transactionManager.onHistoryCommitted = { commitTransaction(it) }
    }

    // --- Stack State ---
    fun canUndo(): Boolean = !busy.get() && undoStack.isNotEmpty()
    fun canRedo(): Boolean = !busy.get() && redoStack.isNotEmpty()

    /**
     * Returns the UI label for the current undo action, e.g. "Undo Copy" or "Undo Rename".
     * Returns null if nothing to undo.
     */
    fun getUndoLabel(): String? {
        val tx = undoStack.peek() ?: return null
        val action = tx.ops.firstOrNull { it.undoAction != null }?.undoAction ?: return null
        return "Undo ${action.undoLabel}"
    }

    /**
     * Returns the UI label for the current redo action, e.g. "Redo Copy" or "Redo Rename".
     * Returns null if nothing to redo.
     */
    fun getRedoLabel(): String? {
        val tx = redoStack.peek() ?: return null
        val action = tx.ops.firstOrNull { it.undoAction != null }?.undoAction ?: return null
        return "Redo ${action.undoLabel}"
    }

    // --- History Commit ---
    fun commitTransaction(tx: Transaction) {
        if (!tx.isReversible) return
        pushBounded(undoStack, tx)
        redoStack.clear()
        onStackChanged?.invoke(canUndo(), canRedo())
    }

    /**
     * Pushes onto [stack] and trims the oldest entries from the tail until the stack is back
     * within [MAX_STACK_SIZE]. ArrayDeque pushes at the head, so the tail holds the oldest
     * entries and [Deque.removeLast] drops exactly those.
     */
    private fun pushBounded(stack: Deque<Transaction>, tx: Transaction) {
        stack.push(tx)
        while (stack.size > MAX_STACK_SIZE) {
            stack.removeLast()
        }
    }

    // --- Undo ---
    fun undo(): Boolean {
        if (!canUndo()) return false
        setBusy(true)
        val tx = undoStack.pop()
        
        // Prepare inverse operations from typed UndoAction
        val undoOps = tx.ops
            .filter { it.status == TransactionStatus.COMPLETED && it.undoAction != null }
            .reversed()
            .map { op ->
                val action = op.undoAction!!
                val (src, dest) = when (action) {
                    is UndoAction.TransferUndo -> {
                        // For transfer undo: src = first destination (for routing)
                        val srcUri = action.destinations.firstOrNull() ?: ""
                        val destUri = action.srcDir ?: ""
                        srcUri to destUri
                    }
                    is UndoAction.TrashUndo -> {
                        // For trash undo: src = first trashed URI (for routing)
                        val srcUri = action.trashedUris.firstOrNull() ?: ""
                        val destUri = action.originalUris.firstOrNull() ?: ""
                        srcUri to destUri
                    }
                    is UndoAction.CreateUndo -> {
                        // For create undo: src = created URI
                        action.createdUri to ""
                    }
                    is UndoAction.RenameUndo -> {
                        // For rename undo: src = current URI
                        action.currentUri to ""
                    }
                }
                TransactionOperation(
                    jobId = Uuid.random(),
                    opType = "undo",
                    src = src,
                    dest = dest,
                    undoAction = action
                )
            }

        if (undoOps.isEmpty()) {
            setBusy(false)
            return true
        }

        scope.launch {
            try {
                val tid = transactionManager.startTransaction("Undo: ${tx.description}", isReversible = false)
                undoOps.forEach { op ->
                    transactionManager.addOperation(
                        tid, 
                        op.opType, 
                        op.src, 
                        op.dest, 
                        jobId = op.jobId, 
                        undoAction = op.undoAction
                    )
                }
                
                // The Finished event must be captured, not awaited cold: `events` has replay = 0,
                // so an emission that happens before anyone subscribes is dropped forever.
                // Arm an UNDISPATCHED collector before committing so the subscription is live,
                // and hand the value over through a Deferred instead of a terminal `first()`.
                val finalEvent = CompletableDeferred<TransactionEvent.Finished>()
                val waiter = launch(start = CoroutineStart.UNDISPATCHED) {
                    transactionManager.events
                        .filter { it.tid == tid }
                        .filterIsInstance<TransactionEvent.Finished>()
                        .first {
                            finalEvent.complete(it)
                            true
                        }
                }

                transactionManager.commitTransaction(tid)

                val final = withTimeoutOrNull(UNDO_TIMEOUT_MS) { finalEvent.await() }
                // No-op once the collector already completed the Deferred; on timeout this is
                // what releases the still-suspended collector instead of leaking it.
                waiter.cancel()

                if (final != null && final.status == TransactionStatus.COMPLETED) {
                    pushBounded(redoStack, tx)
                } else {
                    pushBounded(undoStack, tx)
                }
            } catch (e: Exception) {
                pushBounded(undoStack, tx)
            } finally {
                setBusy(false)
                onStackChanged?.invoke(canUndo(), canRedo())
            }
        }
        return true
    }

    // --- Redo ---
    fun redo(): Boolean {
        if (!canRedo()) return false
        setBusy(true)
        val tx = redoStack.pop()

        scope.launch {
            try {
                val tid = transactionManager.startTransaction("Redo: ${tx.description}", isReversible = false)
                tx.ops.forEach { op ->
                    transactionManager.addOperation(
                        tid,
                        op.opType,
                        op.src,
                        op.dest,
                        overwrite = op.overwrite,
                        autoRename = op.autoRename,
                        undoAction = op.undoAction
                    )
                }

                // Same pre-armed collector pattern as undo() — see the comment there.
                val finalEvent = CompletableDeferred<TransactionEvent.Finished>()
                val waiter = launch(start = CoroutineStart.UNDISPATCHED) {
                    transactionManager.events
                        .filter { it.tid == tid }
                        .filterIsInstance<TransactionEvent.Finished>()
                        .first {
                            finalEvent.complete(it)
                            true
                        }
                }

                transactionManager.commitTransaction(tid)

                val final = withTimeoutOrNull(UNDO_TIMEOUT_MS) { finalEvent.await() }
                waiter.cancel()

                if (final != null && final.status == TransactionStatus.COMPLETED) {
                    // Capture fresh undo actions generated during redo execution
                    tx.ops.forEachIndexed { idx, op ->
                        val freshOp = transactionManager.findOperation(tid, op.jobId)
                        if (freshOp != null && freshOp.undoAction != null) {
                            tx.ops[idx] = op.copy(undoAction = freshOp.undoAction)
                        }
                    }
                    pushBounded(undoStack, tx)
                } else {
                    pushBounded(redoStack, tx)
                }
            } catch (e: Exception) {
                pushBounded(redoStack, tx)
            } finally {
                setBusy(false)
                onStackChanged?.invoke(canUndo(), canRedo())
            }
        }
        return true
    }

    private fun setBusy(value: Boolean) {
        busy.set(value)
        onBusyChanged?.invoke(value)
    }
}
