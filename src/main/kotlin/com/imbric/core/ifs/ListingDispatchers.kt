package com.imbric.core.ifs

import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.ExecutorCoroutineDispatcher
import kotlinx.coroutines.newFixedThreadPoolContext

/**
 * Dedicated thread pool for file listing operations.
 * 
 * The Python approach uses 8 threads for BatchProcessorWorker to achieve
 * pipeline overlap: GIO I/O reads ahead while construction workers process
 * previous batches in parallel. This eliminates thread contention between
 * listing and other I/O operations on the shared Dispatchers.IO.
 */
@OptIn(DelicateCoroutinesApi::class)
object ListingDispatchers {
    /**
     * 8-thread pool dedicated to listing workers.
     * Matches Python's BatchProcessorWorker pool size.
     */
    val Listing: ExecutorCoroutineDispatcher = newFixedThreadPoolContext(8, "listing-worker")
    
    /**
     * 4-thread pool dedicated to enrichment workers.
     * Enrichment is CPU-bound (Skia/PixbufLoader) so we use fewer threads.
     */
    val Enrichment: ExecutorCoroutineDispatcher = newFixedThreadPoolContext(4, "enrichment-worker")

    /** Shuts down both thread pools. Safe to call multiple times. */
    fun close() {
        Listing.close()
        Enrichment.close()
    }

    init {
        // Register JVM shutdown hook to clean up native thread pools
        Runtime.getRuntime().addShutdownHook(Thread {
            close()
        })
    }
}
