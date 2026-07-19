package com.imbric.core.ifs.provider

import com.imbric.core.ifs.IOBackend
import kotlinx.coroutines.CoroutineScope

/**
 * LRU cache for [DirState] instances.
 * Ensures that the same URI always returns the same [DirState] object,
 * preventing duplicate monitoring, duplicate GIO calls, and duplicate enrichment.
 *
 * Uses access-ordered [LinkedHashMap] with a configurable max size.
 * When the cache is full, the least-recently-used [DirState] is evicted
 * and fully released via [DirState.destroy].
 *
 * This replaces the previous [WeakReference] approach, which failed because
 * coroutines launched inside [DirState] capture `this` through their lambdas,
 * creating a strong reference path that prevents garbage collection.
 *
 * Backend dispatch: when [backendResolver] is provided, each URI is routed
 * to the correct [IOBackend] by scheme. When null, the hardcoded
 * [fallbackBackend] is used for all URIs (simple mode for tests).
 *
 * This is the Kotlin equivalent of Nautilus's shared directory objects
 * (same URI = same NautilusDirectory).
 *
 * Usage:
 * ```kotlin
 * // Production: dispatch by scheme via BackendRegistry
 * val registry = DirStateRegistry(fallbackBackend, scope) { uri -> BackendRegistry.getIo(uri) }
 *
 * // Tests: single backend, no dispatch
 * val registry = DirStateRegistry(fakeBackend, scope)
 * ```
 */
class DirStateRegistry(
    private val fallbackBackend: IOBackend,
    private val scope: CoroutineScope,
    /** When provided, URIs are dispatched to the correct backend by scheme. */
    private val backendResolver: ((String) -> IOBackend?)? = null,
    /** Optional pipeline timer. Passed to DirState instances for performance tracing. */
    var pipelineTimer: com.imbric.core.ifs.backends.PipelineTimer? = null,
    /** Maximum number of DirState instances to keep in the LRU cache. */
    private val maxSize: Int = DEFAULT_MAX_SIZE
) {
    /** Access-ordered LRU cache. Most-recently-accessed entries are at the tail. */
    private val cache = object : LinkedHashMap<String, DirState>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, DirState>?): Boolean {
            if (size > maxSize && eldest != null) {
                // Evict the least-recently-used DirState — stop its native monitor
                eldest.value.destroy()
                return true
            }
            return false
        }
    }

    /** Synchronization lock for cache access. */
    private val lock = Any()

    /**
     * Resolves the correct [IOBackend] for the given URI.
     * Uses [backendResolver] if available, otherwise falls back to [fallbackBackend].
     */
    private fun resolveBackend(uri: String): IOBackend {
        return backendResolver?.invoke(uri) ?: fallbackBackend
    }

    /**
     * Returns an existing [DirState] for the given URI, or creates a new one.
     * If the cached instance has been destroyed, a new one is created.
     * Thread-safe: uses synchronized access to prevent duplicate creation.
     */
    fun getOrCreate(uri: String): DirState {
        synchronized(lock) {
            val existing = cache[uri]
            if (existing != null && !existing.isDestroyedState) {
                existing.pipelineTimer = pipelineTimer
                return existing
            }
            // Either not cached or destroyed — create fresh
            cache.remove(uri)
            val backend = resolveBackend(uri)
            val fresh = DirState(uri, backend, scope, pipelineTimer = pipelineTimer)
            cache[uri] = fresh
            return fresh
        }
    }

    /**
     * Returns the number of live DirState instances in the cache.
     * Useful for diagnostics and testing.
     */
    val size: Int
        get() = synchronized(lock) { cache.size }

    /**
     * Returns true if a DirState for the given URI exists and is not destroyed.
     */
    fun contains(uri: String): Boolean {
        synchronized(lock) {
            val state = cache[uri] ?: return false
            return !state.isDestroyedState
        }
    }

    /**
     * Removes a specific URI from the cache and stops its monitoring.
     */
    fun remove(uri: String) {
        synchronized(lock) { cache.remove(uri) }?.destroy()
    }

    /**
     * Clears all cached entries and stops their monitoring.
     */
    fun clear() {
        val snapshot = synchronized(lock) {
            val entries = cache.values.toList()
            cache.clear()
            entries
        }
        snapshot.forEach { it.destroy() }
    }

    companion object {
        /** Default maximum number of cached DirState instances. */
        const val DEFAULT_MAX_SIZE = 20
    }
}
