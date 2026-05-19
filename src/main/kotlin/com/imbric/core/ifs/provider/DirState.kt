@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.provider

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.Locality
import com.imbric.core.models.DeepCount
import com.imbric.core.models.FileInfo
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import java.util.Collections
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Live state of an opened directory.
 * Combines initial listing with real-time monitoring and asynchronous enrichment.
 *
 * Owns its own [SupervisorJob] so that cancelling [destroy] releases all coroutine
 * references to `this`, allowing the instance to be garbage-collected even when
 * held in a [DirStateRegistry] with [WeakReference].
 */
class DirState(
    val uri: String,
    private val backend: IOBackend,
    private val parentScope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
    private val strategy: ListingStrategy = ListingStrategy.Standard
) {
    /** Child job tied to this DirState's lifecycle. Cancelled on [destroy]. */
    private val job = SupervisorJob(parentScope.coroutineContext[Job])
    private val scope = CoroutineScope(parentScope.coroutineContext + job)

    /*
     * KNOWN LIMITATION: Memory leak via WeakReference + coroutines
     *
     * The coroutines launched in refresh() and startWatching() capture `this`
     * (the DirState instance) through their lambdas. This creates a strong
     * reference path: CoroutineScope → Job → coroutine lambda → DirState.
     *
     * As long as these coroutines are running, the DirState instance will
     * NEVER be garbage-collected, even when held only via WeakReference in
     * DirStateRegistry. The WeakReference cache effectively becomes a
     * permanent memory leak for every directory visited during the session.
     *
     * TODO: Fix properly when app/ layer is built. Options:
     *  1. Reference counting: UI layer calls retain()/release(), destroy() on 0.
     *  2. LRU eviction: Registry evicts least-recently-used DirStates after N.
     *  3. WeakCoroutine: Launch coroutines that hold WeakReference<DirState>
     *     and self-cancel when the reference is cleared.
     *  4. Explicit lifecycle: ViewModel owns DirState lifecycle, registry is
     *     just a lookup cache (no WeakReference needed).
     *
     * For now, destroy() + DirStateRegistry.isDestroyedState provides a
     * manual escape hatch. The app layer MUST call destroy() when navigating
     * away from a directory.
     */

    private val _items = MutableStateFlow<Map<String, FileInfo>>(emptyMap())
    private val _itemsList = MutableStateFlow<List<FileInfo>>(emptyList())
    
    /**
     * The current list of files in the directory.
     * Updates automatically as the file system changes.
     */
    val items: StateFlow<List<FileInfo>> = _itemsList.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading

    private val _loadError = MutableStateFlow<Exception?>(null)
    /** The last error that occurred during loading, if any. Cleared on next refresh. */
    val loadError: StateFlow<Exception?> = _loadError.asStateFlow()

    /** The type of directory this DirState represents (derived from URI scheme). */
    val directoryType: DirectoryType = DirectoryType.fromUri(uri)

    private val enrichedUris = Collections.synchronizedSet(mutableSetOf<String>())
    private var watchJob: Job? = null
    private var refreshJob: Job? = null
    private val isDestroyed = AtomicBoolean(false)
    /** True if [destroy] has been called. The registry uses this to detect stale entries. */
    val isDestroyedState: Boolean get() = isDestroyed.get()

    init {
        refresh() // refresh() calls startWatching() internally
    }

    /**
     * Forces a full reload of the directory contents.
     * Cancels any in-progress refresh to prevent interleaved data.
     * Restarts monitoring if it was stopped.
     */
    fun refresh() {
        if (isDestroyed.get()) return
        val newJob = scope.launch(ioDispatcher) {
            refreshJob?.cancelAndJoin() // Wait for old job to finish before clearing state
            startWatching() // Ensure monitoring is active after a stop()
            _isLoading.value = true
            _loadError.value = null
            _items.value = emptyMap()
            _itemsList.value = emptyList()
            enrichedUris.clear()
            try {
                strategy.list(backend, uri)
                    .chunked(50)
                    .collect { chunk ->
                        val updatedMap = _items.updateAndGet { current ->
                            current + chunk.associateBy { it.uri }
                        }
                        _itemsList.value = updatedMap.values.toList()
                        // Start enrichment for this chunk
                        chunk.forEach { enrichItem(it) }
                        
                        yield()
                    }
            } catch (e: Exception) {
                _loadError.value = e
            } finally {
                _isLoading.value = false
            }
        }
        refreshJob = newJob
    }

    private fun startWatching() {
        if (isDestroyed.get()) return
        if (!strategy.watchable()) return // Virtual/Search/Starred strategies don't watch
        watchJob?.cancel()
        watchJob = scope.launch(ioDispatcher) {
            // A boundless bucket to catch the GIO signal storm
            val eventChannel = Channel<FileEvent>(Channel.UNLIMITED)
            
            // 1. PRODUCER: Listen to GIO and throw events into the bucket instantly
            launch {
                backend.watch(uri).collect { event ->
                    eventChannel.send(event)
                }
            }
            
            // 2. CONSUMER: The 200ms Storm Catcher
            launch {
                while (isActive) {
                    // Wait until the very first event hits (Suspends efficiently)
                    val firstEvent = eventChannel.receive() 
                    val batch = mutableListOf(firstEvent)
                    
                    // 🔥 THE DEBOUNCE: Wait 200ms to see if a "storm" follows
                    delay(200)
                    
                    // Scoop up all remaining events that arrived during the 200ms
                    while (true) {
                        val nextEvent = eventChannel.tryReceive().getOrNull() ?: break
                        batch.add(nextEvent)
                    }
                    
                    // Process the whole batch in one shot!
                    handleEventBatch(batch)
                }
            }
        }
    }

    private suspend fun handleEventBatch(events: List<FileEvent>) {
        // 1. Separate events into categories
        val urisToFetch = mutableSetOf<String>()
        val urisToRemove = mutableSetOf<String>()
        
        events.forEach { event ->
            when (event) {
                is FileEvent.Created -> urisToFetch.add(event.uri)
                is FileEvent.Modified -> {
                    urisToFetch.add(event.uri)
                    enrichedUris.remove(event.uri) // Force re-enrichment
                }
                is FileEvent.Deleted -> {
                    urisToRemove.add(event.uri)
                    enrichedUris.remove(event.uri)
                }
                is FileEvent.Renamed -> {
                    urisToRemove.add(event.from)
                    enrichedUris.remove(event.from)
                    urisToFetch.add(event.to)
                }
            }
        }

        // 2. Do a BULK fetch for all new/modified files (Way faster than 500 individual fetches)
        val fetchedInfos = if (urisToFetch.isNotEmpty()) {
            backend.getMetadata(urisToFetch.toList()).mapNotNull { it.getOrNull() }
        } else {
            emptyList()
        }

        // 3. Update the StateFlow exactly ONCE for the whole batch
        val updatedMap = _items.updateAndGet { current ->
            var nextMap = current
            urisToRemove.forEach { uri -> nextMap = nextMap - uri }
            fetchedInfos.forEach { info -> nextMap = nextMap + (info.uri to info) }
            nextMap
        }
        _itemsList.value = updatedMap.values.toList()

        // 4. Trigger enrichment in the background for the new files
        fetchedInfos.forEach { enrichItem(it) }
    }

    private fun enrichItem(info: FileInfo) {
        if (!enrichedUris.add(info.uri)) return

        // Fast synchronous enrichment (Emblems)
        val emblems = mutableListOf<String>()
        if (info.isSymlink) emblems.add("emblem-symbolic-link")
        if (!info.isWritable) emblems.add("emblem-readonly")
        
        val customEmblems = info.attributes["metadata::emblems"] as? List<*>
        customEmblems?.filterIsInstance<String>()?.let { emblems.addAll(it) }

        var currentInfo = info
        if (emblems.isNotEmpty()) {
            currentInfo = currentInfo.copy(
                attributes = currentInfo.attributes + mapOf("std::emblems" to emblems)
            )
            updateItem(currentInfo.uri, currentInfo)
        }

        scope.launch(ioDispatcher) {
            // Asynchronous backend enrichment (Pixbuf, .desktop files, etc.)
            val enrichedInfo = backend.enrichMetadata(currentInfo)
            if (enrichedInfo != currentInfo) {
                updateItem(enrichedInfo.uri, enrichedInfo)
                currentInfo = enrichedInfo
            }

            if (currentInfo.isDirectory) {
                val caps = backend.getCapabilities(currentInfo.uri)
                // Latency Guard: skip deep counting on remote backends
                if (caps.locality != Locality.NETWORK && caps.locality != Locality.VIRTUAL) {
                    try {
                        val count = backend.deepCount(currentInfo.uri).last()
                        val countInfo = currentInfo.copy(
                            attributes = currentInfo.attributes + mapOf(
                                "std::deep-count" to count,
                                "std::child-count" to count.totalItems
                            )
                        )
                        updateItem(countInfo.uri, countInfo)
                        currentInfo = countInfo
                    } catch (_: Exception) {
                        // Deep count failed — not critical, skip silently
                    }
                }
            }

            // Mark enrichment complete — used by whenEnriched() readiness flow
            val enrichedMarker = currentInfo.copy(
                attributes = currentInfo.attributes + ("std::enriched" to true)
            )
            updateItem(enrichedMarker.uri, enrichedMarker)
        }
    }

    private fun updateItem(uri: String, info: FileInfo) {
        val updatedMap = _items.updateAndGet { current ->
            current + (uri to info)
        }
        _itemsList.value = updatedMap.values.toList()
    }

    // --- Convenience methods (Nautilus parity) ---

    /** Returns true if the directory contains any items. */
    val isNotEmpty: Boolean
        get() = _items.value.isNotEmpty()

    /** Returns true if the directory contains a file with the given URI. */
    fun containsFile(uri: String): Boolean = _items.value.containsKey(uri)

    /** Returns the FileInfo for the file with the given name, or null if not found. */
    fun getFileByName(name: String): FileInfo? = _itemsList.value.find { it.name == name }

    /**
     * Returns all files in the directory that match the given glob pattern.
     * Compiles the pattern once and filters all items, avoiding per-file regex compilation.
     */
    fun matchPattern(pattern: String): List<FileInfo> {
        val regex = FileInfo.compileGlob(pattern)
        return _itemsList.value.filter { regex.matches(it.name) }
    }

    // --- Readiness flows (Nautilus call_when_ready equivalent) ---

    /**
     * Emits the current item list once the predicate is satisfied and loading is complete.
     * This is the Kotlin equivalent of Nautilus's `call_when_ready()` pattern.
     *
     * Example:
     * ```
     * dirState.whenReady { it.size > 10 }.collect { items ->
     *     println("Got ${items.size} items")
     * }
     * ```
     */
    fun whenReady(predicate: (List<FileInfo>) -> Boolean): Flow<List<FileInfo>> =
        _itemsList.filter { list -> !_isLoading.value && predicate(list) }.take(1)

    /**
     * Emits the FileInfo for a specific URI once its enrichment is complete
     * (i.e., it has been processed by the enrichment pipeline — emblems assigned,
     * deep count done, etc.).
     *
     * Checks for the presence of `std::emblems` or `std::deep-count` to distinguish
     * between basic GIO metadata and fully enriched data.
     *
     * Example:
     * ```
     * dirState.whenEnriched("file:///home/user/photo.jpg").collect { info ->
     *     println("Dimensions: ${info.attributes["std::dimensions"]}")
     * }
     * ```
     */
    fun whenEnriched(uri: String): Flow<FileInfo> =
        _itemsList.mapNotNull { list ->
            list.find { info ->
                info.uri == uri && info.attributes.containsKey("std::enriched")
            }
        }.take(1)

    // --- Lifecycle ---

    /**
     * Stops monitoring and enrichment, but keeps the current data in memory.
     * Use this when a view navigates away but you want fast re-open via [DirStateRegistry].
     * Call [refresh] to restart monitoring.
     */
    fun stop() {
        watchJob?.cancel()
        watchJob = null
    }

    /**
     * Fully destroys this DirState: stops monitoring, clears all data, and marks it as destroyed.
     * After calling destroy(), this instance should not be reused.
     * The [DirStateRegistry] will create a fresh instance if the same URI is requested again.
     */
    fun destroy() {
        if (isDestroyed.compareAndSet(false, true)) {
            job.cancel() // Cancels all child coroutines, releasing references to `this`
            _items.value = emptyMap()
            _itemsList.value = emptyList()
            _isLoading.value = false
            _loadError.value = null
            enrichedUris.clear()
        }
    }
}

/**
 * Utility to batch flow emissions into lists.
 */
private fun <T> Flow<T>.chunked(size: Int): Flow<List<T>> = flow {
    val chunk = mutableListOf<T>()
    collect { value ->
        chunk.add(value)
        if (chunk.size >= size) {
            emit(chunk.toList())
            chunk.clear()
        }
    }
    if (chunk.isNotEmpty()) {
        emit(chunk)
    }
}
