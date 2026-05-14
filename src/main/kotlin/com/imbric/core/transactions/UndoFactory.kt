@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.transactions.models.TransactionOperation
import kotlin.uuid.ExperimentalUuidApi

/**
 * Factory for creating inverse payloads (Undo DNA) for transaction operations.
 */
object UndoFactory {
    fun createInverse(op: TransactionOperation): Map<String, Any?>? {
        val target = op.resultPath ?: op.dest
        return when (op.opType) {
            "copy" -> mapOf(
                "action" to "undo_copy",
                "target" to target
            )
            "move" -> mapOf(
                "action" to "undo_move",
                "target" to target,
                "dest" to op.src
            )
            "rename" -> mapOf(
                "action" to "undo_rename",
                "target" to target,
                "dest" to op.src
            )
            // Trash undo is usually handled by the TrashManager/TrashItem, 
            // but we could support it here if needed.
            else -> null
        }
    }
}
