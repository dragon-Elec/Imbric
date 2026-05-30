@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.provider

import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.ListingDispatchers
import com.imbric.core.ifs.Locality
import com.imbric.core.models.DeepCount
import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.delay
import kotlin.coroutines.EmptyCoroutineContext
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
    private val ioDispatcher: CoroutineDispatcher = ListingDispatchers.Listing,
    private val strategy: ListingStrategy = ListingStrategy.Standard,
    /** Optional pipeline timing tracer for performance debugging. */
    var pipelineTimer: com.imbric.core.ifs.backends.PipelineTimer? = null
) {
    private val enrichmentSemaphore = Semaphore(4)
    private val enrichmentChannel = Channel<FileInfo>(Channel.UNLIMITED)
    private val enrichmentResults = Channel<FileInfo>(Channel.UNLIMITED)
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

    private val _items = MutableStateFlow<Map<String, FileEntry>>(emptyMap())
    private val _itemsList = MutableStateFlow<List<FileEntry>>(emptyList())
    private val _uiUpdateChannel = Channel<Unit>(Channel.CONFLATED)
    
    /**
     * The current list of files in the directory.
     * Updates automatically as the file system changes.
     */
    val items: StateFlow<List<FileEntry>> = _itemsList.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
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

    /** The current sort key. UI sets this, DirState adapts attribute fetching. */
    var sortKey: SortKey = SortKey.NAME

    private val fileCache = LinkedHashMap<String, FileEntry>(512)

    init {
        refresh() // refresh() calls startWatching() internally
        startEnrichmentWorkers()
        startEnrichmentBatcher()
    }

    private fun startEnrichmentWorkers() {
        repeat(4) {
            scope.launch(ioDispatcher) {
                for (info in enrichmentChannel) {
                    val enriched = try {
                        val res = backend.enrichMetadata(info)
                        res.copy(attributes = res.attributes + ("std::enriched" to true))
                    } catch (_: CancellationException) {
                        break
                    } catch (_: Exception) {
                        info.copy(attributes = info.attributes + ("std::enriched" to true))
                    }
                    enrichmentResults.send(enriched)
                }
            }
        }
    }

    private fun startEnrichmentBatcher() {
        scope.launch(ioDispatcher) {
            while (isActive) {
                // Suspend until at least one enriched result arrives
                val first = enrichmentResults.receive()
                val batch = mutableListOf<FileInfo>(first)
                // Drain any additional results already buffered
                while (true) {
                    val extra = enrichmentResults.tryReceive().getOrNull() ?: break
                    batch.add(extra)
                    if (batch.size >= 50) break
                }
                flushEnrichmentBatch(batch)
            }
        }
    }

    private fun flushEnrichmentBatch(batch: List<FileEntry>) {
        val mutable = _items.value.toMutableMap()
        batch.forEach { mutable[it.uri] = it }
        _items.value = mutable
        _itemsList.value = mutable.values.toList()
    }

    /**
     * Re-loads the directory contents and updates the cache.
     * Cancels any in-progress refresh to prevent interleaved data.
     * Restarts monitoring if it was stopped.
     */
    fun refresh() {
        if (isDestroyed.get()) return
        val oldJob = refreshJob
        val timer = pipelineTimer
        val timerContext = timer?.asContextElement() ?: EmptyCoroutineContext
        // Set loading flag SYNCHRONOUSLY before launching coroutine to prevent onActive() race
        _isLoading.value = true
        _loadError.value = null
        val newJob = scope.launch(ioDispatcher + timerContext) {
            oldJob?.cancelAndJoin()
            startWatching()
            timer?.mark("dir_refresh_start")
            enrichedUris.clear()
            var localItems = HashMap<String, FileEntry>(512)

            try {
                val allItems = strategy.list(backend, uri, sortKey)

                localItems = HashMap<String, FileEntry>(allItems.size + 16)
                for (item in allItems) {
                    val cached = fileCache[item.uri]
                    val itemToStore = if (cached != null && cached.modifiedTime == item.modifiedTime && cached.size == item.size) {
                        cached
                    } else {
                        item
                    }
                    localItems[itemToStore.uri] = itemToStore
                }

                // Sort and emit once
                val sorted = localItems.values.sortedWith(FileEntry.comparatorFor(sortKey))
                _items.value = sorted.associateBy { it.uri }
                _itemsList.value = sorted
                timer?.mark("first_chunk_rendered", itemCount = sorted.size)
                timer?.mark("dir_list_done", itemCount = sorted.size)

                // Update cache
                fileCache.clear()
                fileCache.putAll(localItems)

                // Enrichment AFTER listing completes
                localItems.values.filterIsInstance<FileInfo>().forEach { enrichItem(it) }
            } catch (e: Exception) {
                if (e !is kotlinx.coroutines.CancellationException) {
                    _loadError.value = e
                }
            } finally {
                _isLoading.value = false
                timer?.mark("dir_refresh_done", itemCount = localItems.size)
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
            // Inline emblem update — cheap, keeps UI correct
            val mutable = _items.value.toMutableMap()
            mutable[currentInfo.uri] = currentInfo
            _items.value = mutable
            _itemsList.value = mutable.values.toList()
        }

        // Queue for async heavy lifting (pixbuf, .desktop, etc.)
        enrichmentChannel.trySend(currentInfo)
    }

    /**
     * Viewport-driven enrichment: only enrich items visible in the viewport.
     * Called by the UI when the visible items change (scroll, resize).
     */
    fun enrichVisibleItems(visibleUris: List<String>) {
        val items = _items.value
        visibleUris.forEach { uri ->
            val entry = items[uri] ?: return@forEach
            if (!enrichedUris.contains(uri) && entry is FileInfo) {
                enrichItem(entry)
            }
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

    /** Returns the FileEntry for the file with the given name, or null if not found. */
    fun getFileByName(name: String): FileEntry? = _itemsList.value.find { it.name == name }

    /**
     * Returns all files in the directory that match the given glob pattern.
     * Compiles the pattern once and filters all items, avoiding per-file regex compilation.
     */
    fun matchPattern(pattern: String): List<FileEntry> {
        val regex = FileEntry.compileGlob(pattern)
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
    fun whenReady(predicate: (List<FileEntry>) -> Boolean): Flow<List<FileEntry>> =
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
    fun whenEnriched(uri: String): Flow<FileEntry> =
        _itemsList.mapNotNull { list ->
            list.find { info ->
                info.uri == uri && (info is FileInfo && info.attributes.containsKey("std::enriched"))
            }
        }.take(1)

    // --- Lifecycle ---

    /**
     * Called when this DirState becomes actively viewed by the UI.
     * Restarts monitoring and triggers a background check/sync without clearing current items or showing the spinner.
     */
    fun onActive() {
        if (isDestroyed.get()) return
        startWatching()

        // If we are already loading (e.g. from init), don't cancel it
        if (_isLoading.value) return

        // Fast background revalidation (Stale-While-Revalidate)
        val oldJob = refreshJob
        val timer = pipelineTimer
        val timerContext = timer?.asContextElement() ?: EmptyCoroutineContext
        _isLoading.value = true
        val newJob = scope.launch(ioDispatcher + timerContext) {
            oldJob?.cancelAndJoin()
            try {
                timer?.mark("dir_revalidate_start", detail = uri)
                val fetched = mutableMapOf<String, FileEntry>()
                strategy.list(backend, uri, sortKey).forEach { item ->
                    fetched[item.uri] = item
                }
                val current = _items.value
                if (current != fetched) {
                    val sorted = fetched.values.sortedWith(FileEntry.comparatorFor(sortKey))
                    _items.value = sorted.associateBy { it.uri }
                    _itemsList.value = sorted
                    fetched.values.filterIsInstance<FileInfo>().forEach { enrichItem(it) }
                }
                timer?.mark("dir_revalidate_done", detail = uri, itemCount = fetched.size)
            } catch (e: Exception) {
                if (e !is CancellationException) {
                    _loadError.value = e
                }
            } finally {
                _isLoading.value = false
            }
        }
        refreshJob = newJob
    }

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
 * @param initialSize The size of the first chunk (for fast initial render)
 * @param size The size of subsequent chunks (to prevent UI thrashing)
 */
private fun <T> Flow<T>.chunked(initialSize: Int, size: Int): Flow<List<T>> = flow {
    val chunk = mutableListOf<T>()
    var isFirstChunk = true
    collect { value ->
        chunk.add(value)
        val currentTargetSize = if (isFirstChunk) initialSize else size
        if (chunk.size >= currentTargetSize) {
            emit(chunk.toList())
            chunk.clear()
            isFirstChunk = false
        }
    }
    if (chunk.isNotEmpty()) {
        emit(chunk)
    }
}
