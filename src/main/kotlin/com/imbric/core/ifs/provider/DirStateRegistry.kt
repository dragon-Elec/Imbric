package com.imbric.core.ifs.provider

import com.imbric.core.ifs.IOBackend
import kotlinx.coroutines.CoroutineScope
import java.lang.ref.WeakReference
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * Flyweight cache for [DirState] instances.
 * Ensures that the same URI always returns the same [DirState] object,
 * preventing duplicate monitoring, duplicate GIO calls, and duplicate enrichment.
 *
 * Uses [WeakReference] so that [DirState] instances are automatically
 * garbage-collected when no view holds a reference to them.
 *
 * This is the Kotlin equivalent of Nautilus's shared directory objects
 * (same URI = same NautilusDirectory).
 *
 * Usage:
 * ```kotlin
 * val registry = DirStateRegistry(backend, scope)
 * val dirState = registry.getOrCreate("file:///home/user/Documents")
 * // ... use dirState ...
 * dirState.stop()  // Stop monitoring, but keep in cache for fast re-open
 * dirState.destroy()  // Fully remove from cache and stop monitoring
 * ```
 */
class DirStateRegistry(
    private val backend: IOBackend,
    private val scope: CoroutineScope,
    /** Optional pipeline timer. Passed to DirState instances for performance tracing. */
    var pipelineTimer: com.imbric.core.ifs.backends.PipelineTimer? = null
) {
    private val cache = ConcurrentHashMap<String, WeakReference<DirState>>()
    private val accessCount = AtomicInteger(0)

    /**
     * Returns an existing [DirState] for the given URI, or creates a new one.
     * If the cached instance has been garbage-collected or destroyed, a new one is created.
     * Thread-safe: uses [ConcurrentHashMap.computeIfAbsent] to prevent duplicate creation.
     * Has a retry limit to prevent infinite recursion if DirState initialization fails.
     */
    fun getOrCreate(uri: String): DirState {
        var retries = 0
        while (retries < 3) {
            val ref = cache.computeIfAbsent(uri) { WeakReference(DirState(uri, backend, scope, pipelineTimer = pipelineTimer)) }
            val state = ref.get()
            when {
                state == null -> {
                    cache.remove(uri, ref)
                    retries++
                    continue
                }
                state.isDestroyedState -> {
                    cache.remove(uri, ref)
                    retries++
                    continue
                }
                else -> {
                    // Opportunistic sweep every 100 accesses to avoid O(N) on every call
                    if (accessCount.incrementAndGet() % 100 == 0) sweepStale()
                    return state
                }
            }
        }
        // If we exhausted retries, ensure we still return a cached instance
        // to maintain the singleton-per-URI invariant
        return cache.computeIfAbsent(uri) { WeakReference(DirState(uri, backend, scope, pipelineTimer = pipelineTimer)) }
            .get() ?: DirState(uri, backend, scope, pipelineTimer = pipelineTimer)
    }

    /**
     * Returns the number of live (non-collected) DirState instances in the cache.
     * Useful for diagnostics and testing.
     */
    val size: Int
        get() = cache.values.count { it.get() != null }

    /**
     * Returns true if a DirState for the given URI exists and is still alive.
     */
    fun contains(uri: String): Boolean {
        return cache[uri]?.get() != null
    }

    /**
     * Removes a specific URI from the cache and stops its monitoring.
     */
    fun remove(uri: String) {
        cache.remove(uri)?.get()?.stop()
    }

    /**
     * Clears all cached entries and stops their monitoring.
     */
    fun clear() {
        cache.values.forEach { ref -> ref.get()?.stop() }
        cache.clear()
    }

    /**
     * Removes stale WeakReferences that have been garbage-collected.
     * Called opportunistically during getOrCreate().
     */
    private fun sweepStale() {
        val iterator = cache.entries.iterator()
        while (iterator.hasNext()) {
            if (iterator.next().value.get() == null) {
                iterator.remove()
            }
        }
    }
}
