package com.imbric.core.models

data class DiskUsage(
    val totalBytes: Long,
    val availableBytes: Long,
    val usedBytes: Long = totalBytes - availableBytes,
    val percentUsed: Double = if (totalBytes > 0) (usedBytes.toDouble() / totalBytes) else 0.0
)
