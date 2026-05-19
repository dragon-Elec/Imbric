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
    private val undoStack: Deque<Transaction> = ArrayDeque()
    private val redoStack: Deque<Transaction> = ArrayDeque()
    private var busy = false

    // --- Callbacks for UI ---
    var onStackChanged: ((Boolean, Boolean) -> Unit)? = null
    var onBusyChanged: ((Boolean) -> Unit)? = null

    fun attach() {
        transactionManager.onHistoryCommitted = { commitTransaction(it) }
    }

    // --- Stack State ---
    fun canUndo(): Boolean = !busy && undoStack.isNotEmpty()
    fun canRedo(): Boolean = !busy && redoStack.isNotEmpty()

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
        if (tx.status != TransactionStatus.COMPLETED) return
        undoStack.push(tx)
        redoStack.clear()
        onStackChanged?.invoke(canUndo(), canRedo())
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
                
                val finishedFlow = transactionManager.events
                    .filter { it.tid == tid }
                    .filterIsInstance<TransactionEvent.Finished>()

                transactionManager.commitTransaction(tid)

                val finalEvent = finishedFlow.first()

                if (finalEvent.status == TransactionStatus.COMPLETED) {
                    redoStack.push(tx)
                } else {
                    undoStack.push(tx)
                }
            } catch (e: Exception) {
                undoStack.push(tx)
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

                val finishedFlow = transactionManager.events
                    .filter { it.tid == tid }
                    .filterIsInstance<TransactionEvent.Finished>()

                transactionManager.commitTransaction(tid)

                val finalEvent = finishedFlow.first()

                if (finalEvent.status == TransactionStatus.COMPLETED) {
                    // Capture fresh undo actions generated during redo execution
                    tx.ops.forEachIndexed { idx, op ->
                        val freshOp = transactionManager.findOperation(tid, op.jobId)
                        if (freshOp != null && freshOp.undoAction != null) {
                            tx.ops[idx] = op.copy(undoAction = freshOp.undoAction)
                        }
                    }
                    undoStack.push(tx)
                } else {
                    redoStack.push(tx)
                }
            } catch (e: Exception) {
                redoStack.push(tx)
            } finally {
                setBusy(false)
                onStackChanged?.invoke(canUndo(), canRedo())
            }
        }
        return true
    }

    private fun setBusy(value: Boolean) {
        busy = value
        onBusyChanged?.invoke(value)
    }
}
