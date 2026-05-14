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
        val opsToProcess = if (isUndo) tx.ops.reversed() else tx.ops
        var success = true
        var message = ""
        
        for (op in opsToProcess) {
            if (op.status != TransactionStatus.COMPLETED) continue
            
            try {
                val result = if (isUndo) {
                    val inverse = op.inversePayload ?: continue
                    executeInversePayload(inverse)
                } else {
                    executeOriginalOperation(op)
                }
                
                if (!result) {
                    success = false
                    message = "Failed to ${if (isUndo) "undo" else "redo"} operation: ${op.src}"
                    break
                }
            } catch (e: Exception) {
                success = false
                message = e.message ?: "Unknown error"
                break
            }
        }
        
        if (success) {
            if (isUndo) {
                redoStack.push(tx)
            } else {
                undoStack.push(tx)
            }
        }
        
        setBusy(false)
        onOperationFinished?.invoke(success, message)
        onStackChanged?.invoke(canUndo(), canRedo())
    }

    private suspend fun executeInversePayload(payloadMap: Map<String, Any?>): Boolean {
        val target = payloadMap["target"] as? String ?: return false
        val backend = backendRegistry.getIo(target) ?: return false
        
        val payload = InversePayload(
            action = payloadMap["action"] as? String ?: "",
            target = target,
            dest = payloadMap["dest"] as? String,
            backendId = payloadMap["backendId"] as? String
        )
        
        return backend.executeInverse(payload).isSuccess
    }

    private suspend fun executeOriginalOperation(op: TransactionOperation): Boolean {
        val backend = backendRegistry.getIo(op.src) ?: return false
        val job = FileJob(id = Uuid.random(), opType = op.opType, source = op.src, dest = op.dest)
        
        return when (op.opType) {
            "copy" -> { backend.copy(job).collect { }; true }
            "move" -> { backend.move(job).collect { }; true }
            "trash" -> backend.trash(job).isSuccess
            "delete" -> backend.delete(job).isSuccess
            "rename" -> backend.rename(job.source, job.dest).isSuccess
            else -> false
        }
    }

    private fun setBusy(value: Boolean) {
        busy = value
        onBusyChanged?.invoke(value)
    }
}
