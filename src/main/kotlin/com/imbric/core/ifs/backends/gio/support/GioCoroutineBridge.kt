package com.imbric.core.ifs.backends.gio.support

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
import java.lang.ref.Reference

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
 * - `awaitGioAsync` invokes the GIO call synchronously on the calling dispatcher
 *   (no `GLib.idleAdd` hop in the live path); the main-context pump thread owns
 *   callback delivery.
 * - Cancellation propagates to `GCancellable.cancel()`. GLib cancellation is
 *   asynchronous, so the callback may still fire after the coroutine is cancelled —
 *   [pendingCallbacks] keeps it alive across that window.
 *
 * ## Memory Management
 * - java-gi wraps `AsyncReadyCallback` and `FileProgressCallback` in
 *   `ArenaCloseAction.CLEANER`, so native memory is freed when the Java object is GC'd.
 * - **Critical:** The coroutine's state machine holds strong references to the callback
 *   and block (which captures `FileProgressCallback`) while suspended. This prevents
 *   premature GC from freeing the native upcall stub while GIO still holds pointers to it.
 *   Without this, you get SIGSEGV in `upcall_stub_load_target`.
 * - **Cancellation window (P0-1 fix):** GLib cancellation is asynchronous — after the
 *   coroutine continuation is released on cancel, the main-context pump thread can still
 *   invoke the callback (with `G_IO_ERROR_CANCELLED`). The state-machine pin dies with
 *   the continuation, so [pendingCallbacks] holds the strong reference across that window.
 *   **Contract:** `block` must perform exactly one native `_async` call; only the
 *   callback itself may unregister.
 *
 * @see ref/GIO-COROUTINE-BRIDGE.md
 */
object GioCoroutineBridge {

    /**
     * Strong references to callbacks currently registered with native GIO operations.
     *
     * The coroutine state machine pins the callback only while its continuation is alive.
     * On cancellation the continuation is released immediately, but GLib cancellation is
     * asynchronous: the pump thread may still invoke the callback after the Java-side
     * coroutine is gone. Without this set the callback becomes unreachable, its
     * `ArenaCloseAction.CLEANER` frees the upcall-stub arena, and the pending native
     * invocation crashes in `upcall_stub_load_target`.
     *
     * Entries are removed ONLY by the callback itself on entry (native invocation fired,
 * GIO no longer holds the upcall). A native operation that never fires its callback —
 * or a `block` that throws before GIO registration — pins its entry for the process
 * lifetime: a deliberate leak-vs-SIGSEGV trade (a userspace sweep cannot prove a
 * native operation dead).
     */
    private val pendingCallbacks: MutableSet<AsyncReadyCallback> =
        java.util.concurrent.ConcurrentHashMap.newKeySet()

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
            // GC-pinned reference to prevent JIT dead-code elimination.
            // The callback is passed to native code via FFM; Java has no other reference to it.
            // Without this pinning, the callback proxy can be GC'd while GIO still holds a
            // native pointer to the upcall stub, causing SIGSEGV.
            var keepAliveCallback: AsyncReadyCallback? = null

            val result = suspendCancellableCoroutine { cont ->
                val cancellable = Cancellable()

                // 1. NATIVE CALLBACK (C → Kotlin). Local `lateinit var` lets the
                //    callback unregister itself from pendingCallbacks on entry.
                lateinit var callback: AsyncReadyCallback
                callback = AsyncReadyCallback { _, res, _ ->
                    // The native invocation has fired: GIO has released the upcall,
                    // so the cycle-safe strong pin is no longer needed.
                    pendingCallbacks.remove(callback)
                    if (cont.isActive) {
                        try {
                            cont.resume(finish(res))
                        } catch (e: Exception) {
                            cont.resumeWithException(e)
                        }
                    }
                }

                // 2. Pin references to prevent GC while GIO holds native pointers:
                //    - keepAliveCallback bridges the suspend → resume path while the
                //      coroutine state machine is live;
                //    - pendingCallbacks survives the continuation's release on
                //      cancellation, covering the async native-cancel window.
                keepAliveCallback = callback
                pendingCallbacks.add(callback)

                // 3. SAFELY DISPATCH TO GLIB MAIN CONTEXT
                try {
                    block(cancellable, callback)
                } catch (e: Exception) {
                    // Do NOT unregister here: block may have registered the callback
                    // with GIO before throwing, in which case the native invocation
                    // will still fire and unregister itself. A pre-registration throw
                    // leaks one entry by design — cheaper than a use-after-free window.
                    cont.resumeWithException(e)
                }

                // 4. KOTLIN → C CANCELLATION
                cont.invokeOnCancellation {
                    cancellable.cancel()
                }
            }

            // 5. Keep the callback reachable past the suspension point. reachabilityFence
            //    is opaque to dead-code elimination, unlike the old .hashCode() no-op.
            Reference.reachabilityFence(keepAliveCallback)

            result
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
