package com.imbric.core.models

/**
 * Result of a recursive directory count operation.
 * Emitted as intermediate results during counting, and as a final result when complete.
 */
data class DeepCount(
    val directories: Int = 0,
    val files: Int = 0,
    val totalSize: Long = 0L,
    val isComplete: Boolean = false
) {
    val totalItems: Int get() = directories + files
}
