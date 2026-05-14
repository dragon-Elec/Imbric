@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.models.FileJob
import com.imbric.core.models.InversePayload
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi
import java.util.Deque
import java.util.ArrayDeque

/**
 * Stack-based undo/redo for transactions.
 * Orchestrates inversions by submitting them back to TransactionManager.
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

    // --- History Commit ---
    fun commitTransaction(tx: Transaction) {
        if (tx.status != TransactionStatus.COMPLETED) return
        // We only add to undo stack if it's a "fresh" transaction, not an undo/redo result
        // (This is a simplified check; more complex logic might be needed to avoid loops)
        undoStack.push(tx)
        redoStack.clear()
        onStackChanged?.invoke(canUndo(), canRedo())
    }

    // --- Undo ---
    fun undo(): Boolean {
        if (!canUndo()) return false
        setBusy(true)
        val tx = undoStack.pop()
        
        // Prepare inverse operations
        val undoOps = tx.ops
            .filter { it.status == TransactionStatus.COMPLETED && it.inversePayload != null }
            .reversed()
            .map { op ->
                val payloadMap = op.inversePayload!!
                TransactionOperation(
                    jobId = Uuid.random(),
                    opType = "undo",
                    src = payloadMap["target"] as? String ?: "",
                    dest = payloadMap["dest"] as? String ?: "",
                    inversePayload = payloadMap
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
                        inversePayload = op.inversePayload
                    )
                }
                
                // 1. Prepare the flow collection BEFORE committing
                val finishedFlow = transactionManager.events
                    .filter { it.tid == tid }
                    .filterIsInstance<TransactionEvent.Finished>()

                // 2. Commit the transaction
                transactionManager.commitTransaction(tid) { op, _ ->
                    transactionManager.executeBatchJob(tid, op)
                }

                // 3. Wait for completion
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
                         autoRename = op.autoRename
                     )
                 }

                 val finishedFlow = transactionManager.events
                     .filter { it.tid == tid }
                     .filterIsInstance<TransactionEvent.Finished>()

                 transactionManager.commitTransaction(tid) { op, _ ->
                     transactionManager.executeBatchJob(tid, op)
                 }

                 val finalEvent = finishedFlow.first()

                 if (finalEvent.status == TransactionStatus.COMPLETED) {
                     // Capture fresh inverse payloads generated during redo execution
                     // so that a subsequent undo will use the correct DNA.
                     tx.ops.forEachIndexed { idx, op ->
                         val freshOp = transactionManager.findOperation(tid, op.jobId)
                         if (freshOp != null && freshOp.inversePayload != null) {
                             tx.ops[idx] = op.copy(inversePayload = freshOp.inversePayload)
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
