package com.imbric.core.ifs.backends

import kotlinx.coroutines.*
import org.gnome.glib.MainContext
import org.gnome.glib.GLib

/**
 * Shared test utilities for GIO-based tests.
 */
object TestUtils {

    /**
     * Runs [block] with a background GLib main context pump.
     * This is required for GIO async callbacks and idle handlers to fire.
     */
    suspend fun withGlibPump(block: suspend () -> Unit) = coroutineScope {
        var running = true
        val pumpThread = Thread {
            val context = MainContext.default_()
            while (running) {
                try {
                    // Block natively until an event arrives
                    context.iteration(true)
                } catch (e: Exception) {
                }
            }
        }.apply {
            name = "Test-GLib-Pump"
            isDaemon = true
            start()
        }

        try {
            withContext(Dispatchers.IO) { block() }
        } finally {
            running = false
            // Send a dummy event to wake up the pump so it checks 'running' and exits
            GLib.idleAdd(GLib.PRIORITY_DEFAULT) { false }
        }
    }
}
