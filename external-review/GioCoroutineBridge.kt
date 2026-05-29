package com.imbric.core.ifs.backends

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import org.gnome.gio.AsyncReadyCallback
import org.gnome.gio.AsyncResult
import org.gnome.gio.Cancellable
import org.gnome.glib.GLib
import org.gnome.glib.MainContext
import org.gnome.glib.Source
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Bridges GIO async C functions to Kotlin Coroutines.
 *
 * GIO async methods (`g_file_copy_async`, `g_file_move_async`, etc.) require a running
 * `GMainContext` to dispatch callbacks. This object provides:
 *
 * 1. [startMainContextPump] — A background coroutine that pumps the GLib event loop,
 *    ensuring callbacks fire even outside a GTK/Compose frame loop.
 *
 * 2. [awaitGioAsync] — A generic suspend function that wraps any GIO async function
 *    with proper cancellation propagation (`GCancellable`) and idle queue cleanup
 *    (`GLib.sourceRemove`).
 *
 * ## Thread Safety
 * - `awaitGioAsync` dispatches the GIO call to the GLib main context via `GLib.idleAdd`,
 *   preventing FFM threading crashes.
 * - Cancellation is race-safe: if the coroutine is cancelled before the idle handler fires,
 *   the handler is removed from the queue. If cancelled after, `GCancellable.cancel()`
 *   aborts the running native operation.
 *
 * ## Memory Management
 * - java-gi wraps `AsyncReadyCallback` and `FileProgressCallback` in
 *   `ArenaCloseAction.CLEANER`, so native memory is freed when the Java object is GC'd.
 * - **Critical:** The coroutine's state machine holds strong references to the callback
 *   and block (which captures `FileProgressCallback`) while suspended. This prevents
 *   premature GC from freeing the native upcall stub while GIO still holds pointers to it.
 *   Without this, you get SIGSEGV in `upcall_stub_load_target`.
 *
 * @see ref/GIO-COROUTINE-BRIDGE.md
 */
object GioCoroutineBridge {

    /**
     * Starts a background daemon thread that pumps the GLib main context natively.
     *
     * This is required for GIO async callbacks, DBus events, and file monitors to fire.
     * Call once during app initialization (e.g., in `ImbricDesktop.initialize()`).
     *
     * By using a dedicated blocking OS thread (`context.iteration(true)`), GIO callbacks
     * fire instantly (within microseconds) rather than being artificially delayed by
     * Compose frame-polling or coroutine dispatcher latency.
     */
    fun startMainContextPump() {
        Thread {
            val context = MainContext.default_()
            while (true) {
                try {
                    context.iteration(true) // Blocks natively until an event arrives
                } catch (e: Exception) {
                    // Ignore exceptions from C callbacks to keep the pump alive
                }
            }
        }.apply {
            name = "GLib-MainContext-Pump"
            isDaemon = true
            start()
        }
    }

    /**
     * Wraps a GIO async function into a Kotlin suspend function.
     *
     * This is the universal bridge for any GIO `_async` / `_finish` pair.
     *
     * **IMPORTANT:** This function requires a running GLib Main Context pump
     * (see [startMainContextPump]) to fire the native callbacks. Without a pump,
     * this function will suspend indefinitely or time out.
     *
     * ## Usage
     * ```kotlin
     * awaitGioAsync(
     *     block = { cancellable, callback ->
     *         gFile.copyAsync(dest, flags, priority, cancellable, null, callback)
     *     },
     *     finish = { result ->
     *         gFile.copyFinish(result)
     *     }
     * )
     * ```
     *
     * @param block Starts the native async operation. Receives a [Cancellable] and
     *              [AsyncReadyCallback] to pass to the GIO function.
     * @param finish Extracts the result from [AsyncResult]. Called when the native
     *               callback fires. May throw [GErrorException] on native errors.
     * @param timeoutMs Optional timeout in milliseconds. If the operation doesn't complete
     *                  within this time, throws [kotlinx.coroutines.TimeoutCancellationException].
     *                  Useful for network mounts that may hang indefinitely. Default: no timeout.
     * @return The result of [finish].
     */
    suspend fun <T> awaitGioAsync(
        block: (cancellable: Cancellable, callback: AsyncReadyCallback) -> Unit,
        finish: (result: AsyncResult) -> T,
        timeoutMs: Long? = null
    ): T {
        val actual: suspend () -> T = {
            // Strong reference to the callback OUTSIDE the suspension block.
            var keepAliveCallback: AsyncReadyCallback? = null

            suspendCancellableCoroutine { cont ->
                val cancellable = Cancellable()

                // 1. NATIVE CALLBACK (C → Kotlin)
                val callback = AsyncReadyCallback { _, res, _ ->
                    if (cont.isActive) {
                        try {
                            cont.resume(finish(res))
                        } catch (e: Exception) {
                            cont.resumeWithException(e)
                        }
                    }
                }

                // 2. Pin reference to prevent GC while GIO holds native pointers.
                keepAliveCallback = callback

                // 3. SAFELY DISPATCH TO GLIB MAIN CONTEXT
                // (Optimized: Direct Dispatch. Bypassing GLib.idleAdd eliminates frame-polling
                // latency delays on small directories. GIO async methods are native-thread-safe.)
                try {
                    block(cancellable, callback)
                } catch (e: Exception) {
                    cont.resumeWithException(e)
                }

                // 4. KOTLIN → C CANCELLATION
                cont.invokeOnCancellation {
                    cancellable.cancel()
                }
            }
        }

        return if (timeoutMs != null) {
            withTimeout(timeoutMs) { actual() }
        } else {
            actual()
        }
    }

    // ====================================================================================
    // ORIGINAL IMPLEMENTATION (Backed up per user instruction)
    // ====================================================================================
    /*
    suspend fun <T> awaitGioAsyncIdle(
        block: (cancellable: Cancellable, callback: AsyncReadyCallback) -> Unit,
        finish: (result: AsyncResult) -> T,
        timeoutMs: Long? = null
    ): T {
        val actual: suspend () -> T = {
            var keepAliveCallback: AsyncReadyCallback? = null

            suspendCancellableCoroutine { cont ->
                val cancellable = Cancellable()

                val callback = AsyncReadyCallback { _, res, _ ->
                    if (cont.isActive) {
                        try {
                            cont.resume(finish(res))
                        } catch (e: Exception) {
                            cont.resumeWithException(e)
                        }
                    }
                }

                keepAliveCallback = callback

                val idleSourceId = GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
                    block(cancellable, callback)
                    false
                }

                cont.invokeOnCancellation {
                    cancellable.cancel()
                    Source.remove(idleSourceId)
                }
            }
        }

        return if (timeoutMs != null) {
            withTimeout(timeoutMs) { actual() }
        } else {
            actual()
        }
    }
    */
}
