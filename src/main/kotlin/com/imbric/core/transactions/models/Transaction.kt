@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions.models

import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Status of a transaction.
 * Ported from Python TransactionStatus enum.
 */
enum class TransactionStatus {
    PENDING,
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED,
    PARTIAL
}

/**
 * Events emitted by the TransactionManager during operation.
 */
sealed interface TransactionEvent {
    val tid: Uuid
    
    data class Started(override val tid: Uuid, val description: String) : TransactionEvent
    data class Progress(override val tid: Uuid, val pct: Float) : TransactionEvent
    data class FileProgress(override val tid: Uuid, val progress: TransferProgress) : TransactionEvent
    data class Finished(override val tid: Uuid, val status: TransactionStatus) : TransactionEvent
    data class Conflict(
        override val tid: Uuid,
        val jobId: Uuid,
        val src: String,
        val dest: String,
        val srcMeta: com.imbric.core.models.FileInfo,
        val destMeta: com.imbric.core.models.FileInfo
    ) : TransactionEvent
}

/**
 * Single operation within a transaction.
 * Ported from Python TransactionOperation dataclass.
 */
data class TransactionOperation(
    val jobId: Uuid,
    val opType: String,
    val src: String,
    val dest: String,
    val overwrite: Boolean = false,
    val backendId: String? = null,
    val inversePayload: Map<String, Any?>? = null,
    val status: TransactionStatus = TransactionStatus.PENDING,
    val error: String = ""
)

/**
 * Tracks a batch of file operations.
 * Ported from Python Transaction dataclass.
 */
data class Transaction(
    val id: Uuid = Uuid.random(),
    val description: String = "",
    val createdAt: Long = System.currentTimeMillis(),
    val ops: MutableList<TransactionOperation> = mutableListOf(),
    var status: TransactionStatus = TransactionStatus.PENDING,
    var error: String = "",
    var isCommitted: Boolean = false,
    var isReversible: Boolean = true
) {
    val totalOps: Int get() = ops.size
    val completedOps: Int get() = ops.count { it.status == TransactionStatus.COMPLETED }
    val finishedOps: Int get() = ops.count { it.status == TransactionStatus.COMPLETED || it.status == TransactionStatus.FAILED || it.status == TransactionStatus.CANCELLED }
    
    fun addOperation(op: TransactionOperation) {
        ops.add(op)
    }
    
    fun getProgress(): Float {
        if (totalOps == 0) return 0f
        return completedOps.toFloat() / totalOps
    }
    
    fun findOperation(jobId: Uuid): TransactionOperation? {
        return ops.find { it.jobId == jobId }
    }
}
