@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import com.imbric.core.models.UndoAction
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Atomic unit of work for file operations.
 * Ported from Python file_job.py – describes a copy/move/trash/rename job.
 */
data class FileJob(
    val id: Uuid = Uuid.random(),
    val opType: String, // "copy", "move", "trash", "restore", "rename", "undo"
    val source: String,
    val dest: String = "",
    val overwrite: Boolean = false,
    val autoRename: Boolean = false,
    val uiRefreshRateMs: Int = 100,
    val haltOnError: Boolean = false,
    val inversePayload: UndoAction? = null
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
 * Structured query for VFS search operations.
 */
data class VfsQuery(
    val text: String,
    val rootUri: String,
    val mimeFilter: String? = null,
    val recursive: Boolean = true,
    val includeHidden: Boolean = false,
    val maxDepth: Int = Int.MAX_VALUE,
    val contentSearch: Boolean = false,
    val onScanned: ((Int) -> Unit)? = null,
    /** Filter by modification time range. Both are epoch milliseconds. */
    val modifiedAfter: Long? = null,
    val modifiedBefore: Long? = null,
    /** Filter by file size range in bytes. */
    val minSize: Long? = null,
    val maxSize: Long? = null,
    /** Filter by starred/tagged status. */
    val starredOnly: Boolean = false
)

/**
 * Progress update for ongoing operations.
 */
data class TransferProgress(
    val jobId: Uuid,
    val currentFile: String,
    val actualDest: String? = null,
    val inversePayload: UndoAction? = null,
    val completedCount: Int = 0,
    val totalCount: Int = 0,
    val completedSize: Long = 0L,
    val totalSize: Long = 0L
)
