package com.imbric.core.transactions

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers

/**
 * Shared dispatchers for bulk I/O operations to prevent resource exhaustion.
 */
object BulkDispatcher {
    /**
     * Dispatcher for local filesystem operations.
     * Limited to 32 concurrent threads to prevent exhausting OS file descriptors.
     */
    val Local: CoroutineDispatcher = Dispatchers.IO.limitedParallelism(32)

    /**
     * Dispatcher for network/MTP filesystem operations.
     * Limited to 8 concurrent threads to prevent overwhelming remote servers.
     */
    val Network: CoroutineDispatcher = Dispatchers.IO.limitedParallelism(8)
}