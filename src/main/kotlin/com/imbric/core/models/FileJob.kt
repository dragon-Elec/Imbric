@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Atomic unit of work for file operations.
 * Ported from Python file_job.py – describes a copy/move/trash/rename job.
 */
data class FileJob(
    val id: Uuid = Uuid.random(),
    val opType: String, // "copy", "move", "trash", "restore", "rename"
    val source: String,
    val dest: String = "",
    val transactionId: Uuid? = null,
    val cancellable: CancellationToken? = null,
    val overwrite: Boolean = false,
    val autoRename: Boolean = false,
    val items: List<Map<String, Any>> = emptyList(), // For batch operations
    val uiRefreshRateMs: Int = 100,
    val haltOnError: Boolean = false,
    val inversePayload: InversePayload? = null
)

/**
 * Payload for undoing a completed operation.
 * Ported from Python InversePayload TypedDict.
 */
data class InversePayload(
    val action: String, // "undo_copy", "undo_move", etc.
    val target: String,
    val dest: String? = null,
    val newName: String? = null,
    val renameTo: String? = null,
    val tid: Uuid? = null,
    val backendId: String? = null
)

/**
 * Simple cancellation token for cooperative cancellation.
 */
open class CancellationToken {
    private var _isCancelled = false
    val isCancelled: Boolean get() = _isCancelled
    
    fun cancel() { _isCancelled = true }
}

/**
 * Progress update for ongoing operations.
 */
data class TransferProgress(
    val jobId: Uuid,
    val currentFile: String,
    val completedCount: Int = 0,
    val totalCount: Int = 0,
    val completedSize: Long = 0L,
    val totalSize: Long = 0L
)
