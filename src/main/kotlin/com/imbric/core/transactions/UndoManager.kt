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
 * Ported from Python undo_manager.py.
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
    var onOperationFinished: ((Boolean, String) -> Unit)? = null

    // --- Stack State ---
    fun canUndo(): Boolean = !busy && undoStack.isNotEmpty()
    fun canRedo(): Boolean = !busy && redoStack.isNotEmpty()

    // --- History Commit ---
    fun commitTransaction(tx: Transaction) {
        if (tx.status != TransactionStatus.COMPLETED) return
        undoStack.push(tx)
        redoStack.clear()
        onStackChanged?.invoke(canUndo(), canRedo())
    }

    // --- Undo ---
    fun undo() {
        if (!canUndo()) return
        val tx = undoStack.pop()
        setBusy(true)
        onStackChanged?.invoke(canUndo(), canRedo())
        scope.launch {
            performInversion(tx, isUndo = true)
        }
    }

    // --- Redo ---
    fun redo() {
        if (!canRedo()) return
        val tx = redoStack.pop()
        setBusy(true)
        onStackChanged?.invoke(canUndo(), canRedo())
        scope.launch {
            performInversion(tx, isUndo = false)
        }
    }

    // --- Core Inversion Logic ---
    private suspend fun performInversion(tx: Transaction, isUndo: Boolean) {
        val undoJobs = tx.ops
            .filter { it.status == TransactionStatus.COMPLETED && it.inversePayload != null }
            .reversed() // Undo in reverse order of original execution
            .map { op ->
                val payloadMap = op.inversePayload!!
                val payload = InversePayload(
                    action = payloadMap["action"] as? String ?: "",
                    target = payloadMap["target"] as? String ?: "",
                    dest = payloadMap["dest"] as? String,
                    backendId = payloadMap["backendId"] as? String
                )
                
                FileJob(
                    id = Uuid.random(),
                    opType = if (isUndo) "undo" else op.opType,
                    source = if (isUndo) payload.target else op.src,
                    dest = if (isUndo) (payload.dest ?: "") else op.dest,
                    inversePayload = if (isUndo) payload else null
                )
            }

        if (undoJobs.isEmpty()) {
            setBusy(false)
            onStackChanged?.invoke(canUndo(), canRedo())
            return
        }

        // Submit to TransactionManager to execute as a first-class transaction
        val name = if (isUndo) "Undo: ${tx.description}" else "Redo: ${tx.description}"
        transactionManager.submit(undoJobs, name, isReversible = true)
        
        if (isUndo) {
            redoStack.push(tx)
        } else {
            undoStack.push(tx)
        }
        
        setBusy(false)
        onStackChanged?.invoke(canUndo(), canRedo())
    }

    private suspend fun executeInversePayload(payloadMap: Map<String, Any?>): Boolean {
        // Obsolete
        return false
    }

    private fun setBusy(value: Boolean) {
        busy = value
        onBusyChanged?.invoke(value)
    }
}
