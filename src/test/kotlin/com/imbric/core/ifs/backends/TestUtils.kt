package com.imbric.core.ifs.backends

import kotlinx.coroutines.*
import org.gnome.glib.MainContext

/**
 * Shared test utilities for GIO-based tests.
 */
object TestUtils {

    /**
     * Runs [block] with a background GLib main context pump.
     * This is required for GIO async callbacks and idle handlers to fire.
     */
    suspend fun withGlibPump(block: suspend () -> Unit) = coroutineScope {
        val pumpJob = launch(Dispatchers.IO) {
            val context = MainContext.default_()
            while (isActive) {
                // Non-blocking iteration to allow the coroutine to check isActive
                context.iteration(false)
                delay(10)
            }
        }
        try {
            withContext(Dispatchers.IO) { block() }
        } finally {
            pumpJob.cancel()
            pumpJob.join()
        }
    }
}
