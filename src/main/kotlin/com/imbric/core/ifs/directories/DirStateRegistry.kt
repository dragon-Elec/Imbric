package com.imbric.core.ifs.directories

import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.backends.gio.support.PipelineTimer
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
 * to the correct [BackendContract] by scheme. When null, the hardcoded
 * [fallbackBackend] is used for all URIs (simple mode for tests).
 *
 * This is the Kotlin equivalent of Nautilus's shared directory objects
 * (same URI = same NautilusDirectory).
 *
 * Pin model (viewer ownership):
 * - [pin] — an active viewer (open tab) is showing this URI. A pinned URI is never
 *   evicted by the LRU, so its pane can never blank out from under the user.
 * - [unpin] — the viewer navigated away. The instance stays cached for instant
 *   return, but becomes evictable again.
 * - [release] — the viewer closed. Drops the pin and, if the refcount reaches zero,
 *   destroys the instance immediately instead of waiting for eviction.
 *
 * Usage:
 * ```kotlin
 * // Production: dispatch by scheme via BackendRegistry
 * val registry = DirStateRegistry(fallbackBackend, scope) { uri -> BackendRegistry.get(uri) }
 *
 * // Tests: single backend, no dispatch
 * val registry = DirStateRegistry(fakeBackend, scope)
 *
 * // Tab lifecycle
 * val state = registry.pin(uri)   // tab opened
 * registry.unpin(uri)             // navigated away, still cached
 * registry.release(uri)           // tab closed
 * ```
 */
class DirStateRegistry(
    private val fallbackBackend: BackendContract,
    private val scope: CoroutineScope,
    /** When provided, URIs are dispatched to the correct backend by scheme. */
    private val backendResolver: ((String) -> BackendContract?)? = null,
    /** Optional pipeline timer. Passed to DirState instances for performance tracing. */
    var pipelineTimer: PipelineTimer? = null,
    /** Maximum number of DirState instances to keep in the LRU cache. */
    private val maxSize: Int = DEFAULT_MAX_SIZE
) {
    /** Access-ordered LRU cache. Most-recently-accessed entries are at the tail. */
    private val cache = LinkedHashMap<String, DirState>(16, 0.75f, true)

    /** Synchronization lock for cache access. */
    private val lock = Any()

    /** Viewer refcounts per URI. Guarded by [lock]. At 0 (or absent) the URI is evictable. */
    private val pinCounts = HashMap<String, Int>()

    /**
     * Resolves the correct [BackendContract] for the given URI.
     * Uses [backendResolver] if available, otherwise falls back to [fallbackBackend].
     */
    private fun resolveBackend(uri: String): BackendContract {
        return backendResolver?.invoke(uri) ?: fallbackBackend
    }

    /** Current pin count for [uri]. Must be called while holding [lock]. */
    private fun refCountLocked(uri: String): Int = pinCounts[uri] ?: 0

    /**
     * Selects LRU victims and detaches them from [cache] until the cache fits [maxSize].
     * Pinned URIs are skipped, so an over-budget cache can temporarily retain extra entries.
     *
     * Must be called while holding [lock]. This only detaches the victims; the caller
     * destroys them after releasing the lock.
     */
    private fun evictOverflowLocked(): List<DirState> {
        if (cache.size <= maxSize) return emptyList()

        // Access-ordered LinkedHashMap iterates eldest-first, so head = LRU.
        // Snapshot the keys first: removing while walking the live key set is unsafe.
        val eldestFirst: List<String> = ArrayList(cache.keys)
        val victimUris = ArrayList<String>()
        for (candidate in eldestFirst) {
            if (cache.size - victimUris.size <= maxSize) break
            if (refCountLocked(candidate) > 0) continue
            victimUris.add(candidate)
        }

        val victims = ArrayList<DirState>(victimUris.size)
        victimUris.forEach { victimUri -> cache.remove(victimUri)?.let { victims.add(it) } }
        return victims
    }

    /**
     * Returns an existing [DirState] for the given URI, or creates a new one.
     * If the cached instance has been destroyed, a new one is created.
     * Thread-safe: uses synchronized access to prevent duplicate creation.
     */
    fun getOrCreate(uri: String): DirState {
        var evicted: List<DirState> = emptyList()
        val state = synchronized(lock) {
            val existing = cache[uri]
            if (existing != null && !existing.isDestroyedState) {
                existing.pipelineTimer = pipelineTimer
                return@synchronized existing
            }
            // Either not cached or destroyed — create fresh
            cache.remove(uri)
            val backend = resolveBackend(uri)
            val fresh = DirState(uri, backend, scope, pipelineTimer = pipelineTimer)
            cache[uri] = fresh
            evicted = evictOverflowLocked()
            fresh
        }
        // Destroy evicted states *after* leaving the synchronized block: destroy() runs
        // teardown callbacks that can re-enter getOrCreate, and calling it inside the
        // LinkedHashMap mutation would corrupt the cache mid-insert.
        evicted.forEach { it.destroy() }
        return state
    }

    /**
     * Returns the [DirState] for [uri] and registers an active viewer, making the
     * instance immune to LRU eviction until the matching [unpin] or [release].
     */
    fun pin(uri: String): DirState {
        val state = getOrCreate(uri)
        synchronized(lock) { pinCounts[uri] = refCountLocked(uri) + 1 }
        return state
    }

    /**
     * Drops one viewer reference for [uri], floored at zero. The cached [DirState] is
     * left intact — it simply becomes evictable again.
     */
    fun unpin(uri: String) {
        synchronized(lock) {
            val current = pinCounts[uri] ?: return
            if (current <= 1) pinCounts.remove(uri) else pinCounts[uri] = current - 1
        }
    }

    /**
     * Drops one viewer reference for [uri] and, if no viewers remain, removes the entry
     * from the cache and destroys it immediately.
     */
    fun release(uri: String) {
        unpin(uri)
        val state = synchronized(lock) {
            if (refCountLocked(uri) > 0) null else cache.remove(uri)
        }
        state?.destroy()
    }

    /** Returns true when at least one viewer has pinned [uri] and is blocking eviction. */
    fun isPinned(uri: String): Boolean {
        return synchronized(lock) { refCountLocked(uri) > 0 }
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
