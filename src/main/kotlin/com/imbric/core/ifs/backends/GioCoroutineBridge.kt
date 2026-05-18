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
     * Starts a background coroutine that pumps the GLib main context.
     *
     * This is required for GIO async callbacks, DBus events, and file monitors to fire.
     * Call once during app initialization (e.g., in `ImbricDesktop.initialize()`).
     *
     * Uses `Dispatchers.IO` because `MainContext.iteration(mayBlock = true)` blocks
     * the calling thread until an event arrives.
     *
     * For Compose UI, prefer `MainContextPump.kt` which integrates with the frame loop.
     * This pump is for non-UI contexts (tests, headless mode, background services).
     */
    fun startMainContextPump(scope: CoroutineScope) {
        scope.launch(Dispatchers.IO) {
            val context = MainContext.default_()
            while (isActive) {
                context.iteration(true) // blocks until event arrives
            }
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
            // Kotlin stores this in the coroutine's state machine, keeping it
            // reachable as long as the coroutine is suspended. This prevents the
            // FFM upcall stub from being GC'd while GIO still holds native pointers.
            var keepAliveCallback: AsyncReadyCallback? = null

            suspendCancellableCoroutine { cont ->
                val cancellable = Cancellable()

                // 1. NATIVE CALLBACK (C → Kotlin)
                // MUST check isActive before resuming. If the coroutine was cancelled
                // (timeout or user action), GIO still fires the native callback with
                // G_IO_ERROR_CANCELLED a few ms later. Calling resume() on a completed
                // continuation throws IllegalStateException.
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
                // We intentionally do NOT null this in a finally block — during cancellation,
                // GIO still holds a native pointer and may fire the callback a few ms later.
                // If we nulled it here, the GC could free the FFM upcall stub mid-flight,
                // causing SIGSEGV. The reference is collected naturally when this lambda
                // goes out of scope (after GIO has fired and the coroutine has completed).
                keepAliveCallback = callback

                // 3. SAFELY DISPATCH TO GLIB MAIN CONTEXT
                // We capture the ID as a val to avoid cross-thread mutation races.
                val idleSourceId = GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
                    block(cancellable, callback)
                    false
                }

                // 4. KOTLIN → C CANCELLATION
                cont.invokeOnCancellation {
                    cancellable.cancel()
                    // Source.remove is idempotent and thread-safe.
                    // If the idle task already ran, this does nothing.
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
}
