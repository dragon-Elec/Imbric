@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.provider

import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.ListingDispatchers
import com.imbric.core.ifs.Locality

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

    private data class DeltaState(
        val additions: Map<String, FileInfo> = emptyMap(),
        val deletions: Set<String> = emptySet(),
        val enrichments: Map<String, FileInfo> = emptyMap()
    )

    private var _baseDirectory: ListingDirectory = ListingDirectory(0)
    private var _compositeView: EnrichedListingView? = null
    private val _deltas = MutableStateFlow(DeltaState())
    private val _itemsList = MutableStateFlow<List<FileEntry>>(emptyList())

    private fun rebuildComposite() {
        val base = _baseDirectory
        val deltas = _deltas.value
        // Create a NEW immutable view on every rebuild — identity equality forces StateFlow emission
        val composite = EnrichedListingView(
            base = base,
            comparator = FileEntry.comparatorFor(sortKey),
            additions = deltas.additions,
            deletions = deltas.deletions,
            enrichments = deltas.enrichments
        )
        _compositeView = composite
        _itemsList.value = composite
    }
    
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
                    val enriched = enrichmentSemaphore.withPermit {
                        try {
                            val res = backend.enrichMetadata(info)
                            res.copy(attributes = res.attributes + ("std::enriched" to true))
                        } catch (_: CancellationException) {
                            throw CancellationException()
                        } catch (_: Exception) {
                            info.copy(attributes = info.attributes + ("std::enriched" to true))
                        }
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
        val current = _deltas.value
        val newEnrichments = current.enrichments + batch.filterIsInstance<FileInfo>().associateBy { it.uri }
        _deltas.value = current.copy(enrichments = newEnrichments)
        rebuildComposite()
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

            try {
                val allItems = strategy.list(backend, uri, sortKey)

                val dir = ListingDirectory(allItems.size + 16)
                val enrichable = mutableListOf<FileInfo>()
                for (item in allItems) {
                    val cached = fileCache[item.uri]
                    val itemToStore = if (cached != null && cached.modifiedTime == item.modifiedTime && cached.size == item.size) {
                        cached
                    } else {
                        item
                    }
                    dir.add(itemToStore)
                    // Track FileInfo items for enrichment (before SoA flattens them)
                    if (itemToStore is FileInfo) enrichable.add(itemToStore)
                }
                dir.sortWith(FileEntry.comparatorFor(sortKey))
                dir.buildUriIndex()

                // Clear deltas and build composite
                val comparator = FileEntry.comparatorFor(sortKey)
                val composite = EnrichedListingView(
                    base = dir,
                    comparator = comparator,
                    additions = emptyMap(),
                    deletions = emptySet(),
                    enrichments = emptyMap()
                )
                _baseDirectory = dir
                _compositeView = composite
                _deltas.value = DeltaState()
                _itemsList.value = composite

                timer?.mark("first_chunk_rendered", itemCount = dir.size)
                timer?.mark("dir_list_done", itemCount = dir.size)

                // Update cache
                fileCache.clear()
                for (i in 0 until dir.size) {
                    fileCache[dir.getUri(i)] = dir.get(i)
                }

                // Enrichment AFTER listing — pass rebuild=false, rebuild once after loop
                for (info in enrichable) {
                    enrichItem(info, rebuild = false)
                }
                rebuildComposite()
            } catch (e: Exception) {
                if (e !is kotlinx.coroutines.CancellationException) {
                    _loadError.value = e
                }
            } finally {
                _isLoading.value = false
                timer?.mark("dir_refresh_done", itemCount = _baseDirectory.size)
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
        val urisToFetch = mutableSetOf<String>()
        val urisToRemove = mutableSetOf<String>()
        
        events.forEach { event ->
            when (event) {
                is FileEvent.Created -> urisToFetch.add(event.uri)
                is FileEvent.Modified -> {
                    urisToFetch.add(event.uri)
                    enrichedUris.remove(event.uri)
                }
                is FileEvent.Deleted -> {
                    urisToRemove.add(event.uri)
                    enrichedUris.remove(event.uri)
                }
                is FileEvent.Renamed -> {
                    urisToRemove.add(event.from)
                    enrichedUris.remove(event.from)
                    // Only fetch destination if it belongs to this directory
                    val toParent = event.to.substringBeforeLast("/")
                    if (toParent == uri.removeSuffix("/")) {
                        urisToFetch.add(event.to)
                    }
                }
            }
        }

        val fetchedInfos = if (urisToFetch.isNotEmpty()) {
            backend.getMetadata(urisToFetch.toList()).mapNotNull { it.getOrNull() }
        } else {
            emptyList()
        }

        // Update delta layer atomically — clean up cross-references
        val current = _deltas.value
        val nextAdditions = current.additions.toMutableMap()
        val nextDeletions = current.deletions.toMutableSet()

        // Deleted files: remove from additions (was created, now deleted)
        urisToRemove.forEach { uri ->
            nextAdditions.remove(uri)
            nextDeletions.add(uri)
        }

        // New/modified files: remove from deletions (was deleted, now re-created)
        fetchedInfos.forEach { info ->
            nextAdditions[info.uri] = info
            nextDeletions.remove(info.uri)
        }

        _deltas.value = current.copy(
            additions = nextAdditions,
            deletions = nextDeletions
        )
        rebuildComposite()

        fetchedInfos.forEach { enrichItem(it) }
    }

    private fun enrichItem(info: FileInfo, rebuild: Boolean = true) {
        if (!enrichedUris.add(info.uri)) return

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
            val current = _deltas.value
            _deltas.value = current.copy(enrichments = current.enrichments + (currentInfo.uri to currentInfo))
            if (rebuild) rebuildComposite()
        }

        enrichmentChannel.trySend(currentInfo)
    }

    /**
     * Viewport-driven enrichment: only enrich items visible in the viewport.
     * Called by the UI when the visible items change (scroll, resize).
     */
    fun enrichVisibleItems(visibleUris: List<String>) {
        val deltas = _deltas.value
        visibleUris.forEach { uri ->
            if (enrichedUris.contains(uri)) return@forEach
            // Check additions/enrichments first (these are FileInfo objects)
            val deltaEntry = deltas.additions[uri] ?: deltas.enrichments[uri]
            if (deltaEntry != null) {
                if (!deltaEntry.isDirectory) enrichItem(deltaEntry)
                return@forEach
            }
            // For base directory entries, look up the original FileInfo from fileCache
            val idx = _baseDirectory.findIndex(uri)
            if (idx == -1) return@forEach
            val cached = fileCache[uri]
            if (cached is FileInfo && !cached.isDirectory) {
                enrichItem(cached)
            }
        }
    }

    // --- Convenience methods (Nautilus parity) ---

    /** Returns true if the directory contains any items. */
    val isNotEmpty: Boolean
        get() = _itemsList.value.isNotEmpty()

    /** Returns true if the directory contains a file with the given URI. */
    fun containsFile(uri: String): Boolean {
        val deltas = _deltas.value
        if (uri in deltas.deletions) return false
        if (uri in deltas.additions) return true
        return _baseDirectory.containsUri(uri)
    }

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
        if (_isLoading.value) return

        val oldJob = refreshJob
        val timer = pipelineTimer
        val timerContext = timer?.asContextElement() ?: EmptyCoroutineContext
        _isLoading.value = true
        val newJob = scope.launch(ioDispatcher + timerContext) {
            oldJob?.cancelAndJoin()
            try {
                timer?.mark("dir_revalidate_start", detail = uri)
                val fetched = strategy.list(backend, uri, sortKey)

                // Build new ListingDirectory
                val dir = ListingDirectory(fetched.size + 16)
                val enrichable = mutableListOf<FileInfo>()
                fetched.forEach {
                    dir.add(it)
                    if (it is FileInfo) enrichable.add(it)
                }
                dir.sortWith(FileEntry.comparatorFor(sortKey))
                dir.buildUriIndex()

                // Compare with current base (quick size + content check)
                val current = _baseDirectory
                var changed = dir.size != current.size
                if (!changed) {
                    for (i in 0 until dir.size) {
                        if (dir.getUri(i) != current.getUri(i) || dir.get(i).size != current.get(i).size) {
                            changed = true
                            break
                        }
                    }
                }

                if (changed) {
                    val comparator = FileEntry.comparatorFor(sortKey)
                    val composite = EnrichedListingView(
                        base = dir,
                        comparator = comparator,
                        additions = emptyMap(),
                        deletions = emptySet(),
                        enrichments = emptyMap()
                    )
                    _baseDirectory = dir
                    _compositeView = composite
                    _deltas.value = DeltaState()
                    _itemsList.value = composite

                    for (info in enrichable) {
                        enrichItem(info, rebuild = false)
                    }
                    rebuildComposite()
                }
                timer?.mark("dir_revalidate_done", detail = uri, itemCount = dir.size)
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
            job.cancel()
            _baseDirectory = ListingDirectory(0)
            _compositeView = null
            _deltas.value = DeltaState()
            _itemsList.value = emptyList()
            _isLoading.value = false
            _loadError.value = null
            enrichedUris.clear()
        }
    }
}


