@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.directories

import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.ListingDispatchers
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.backends.gio.support.PipelineTimer

import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.delay
import kotlin.coroutines.EmptyCoroutineContext
import java.util.Collections
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

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
    private val backend: BackendContract,
    private val parentScope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher = ListingDispatchers.Listing,
    private val strategy: ListingStrategy = ListingStrategy.Standard,
    /** Optional pipeline timing tracer for performance debugging. */
    var pipelineTimer: PipelineTimer? = null
) {
    /**
     * Serializes writes to _baseDirectory, _deltas, _itemsList and fileCache across
     * refresh/onActive/handleEventBatch/flushEnrichmentBatch/enrichItem.
     * Not reentrant — never call a suspending helper that takes it again from inside a
     * `withLock` block (see [enrichItemLocked]).
     */
    private val stateMutex = Mutex()
    private val enrichmentSemaphore = Semaphore(4)
    private val enrichmentChannel = Channel<FileInfo>(Channel.UNLIMITED)
    private val enrichmentResults = Channel<FileInfo>(Channel.UNLIMITED)
    /** Child job tied to this DirState's lifecycle. Cancelled on [destroy]. */
    private val job = SupervisorJob(parentScope.coroutineContext[Job])
    private val scope = CoroutineScope(parentScope.coroutineContext + job)

    /*
     * Lifecycle: coroutines capture `this` via lambdas, preventing GC while running.
     * Fixed: DirStateRegistry uses LRU eviction (max 20) and calls destroy() on eviction,
     * which cancels all coroutines via job.cancel() and releases the strong reference.
     * See DirStateRegistry.removeEldestEntry() for the eviction logic.
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

    /**
     * Emission counter. Every composite emission bumps it exactly once, so a consumer can
     * tell "the listing was re-published" apart from "the listing was re-sorted in place"
     * (both of which must produce a *new* view identity, see [publish]) without having to
     * diff two lists.
     */
    private val emissionRevision = AtomicInteger(0)
    private val _revision = MutableStateFlow(0)

    /** Monotonic counter incremented once per composite emission. Starts at 0. */
    val revision: StateFlow<Int> = _revision.asStateFlow()

    /**
     * The single emission point for the listing. Both the view reference and the public
     * [items] flow are written here, together with the revision bump, so no code path can
     * publish a composite without being counted.
     *
     * Called from inside [stateMutex.withLock] blocks (refresh/onActive/handleEventBatch/
     * enrichItem/flushEnrichmentBatch) and from setSortKey's lock block — the reads of
     * `_baseDirectory`/`_deltas` that produced [composite] happened under the same lock, so
     * no extra locking belongs here and this stays a plain non-suspend function.
     */
    private fun publish(composite: EnrichedListingView) {
        _compositeView = composite
        _itemsList.value = composite
        _revision.value = emissionRevision.incrementAndGet()
    }

    /**
     * Builds a fresh [EnrichedListingView] from the current base + deltas and publishes it
     * via [publish]. Callers must hold [stateMutex] (the rebuild path is the one place
     * where base, deltas and comparator are read as a consistent triple).
     */
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
        publish(composite)
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

    /**
     * Monotonic loading generation shared by [refresh] and [onActive] (both drive the
     * spinner and both install themselves as `refreshJob`). Each new load claims the
     * next epoch *before* launching, so a superseded job — whose `finally` runs while
     * the newer one is joining it — can tell it is stale and must not clear
     * `_isLoading` or publish a load error over the newer load's state.
     */
    private val loadEpoch = AtomicLong(0L)

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

    /**
     * Changes the sort key and re-sorts the already-loaded listing.
     *
     * No re-listing is performed: [FileEntry.listingAttributesFor] now fetches
     * `time::modified` for every sort key, so [FileEntry.comparatorFor] can order the local
     * struct-of-arrays listing correctly for any key. A re-list would pay a full GIO
     * enumeration (plus enrichment re-queueing) purely to change row order.
     *
     * The re-sort mutates [_baseDirectory] and the following [rebuildComposite] reads the
     * deltas and comparator, so both run inside one [stateMutex] block — same discipline as
     * [refresh]/[onActive], and an in-flight refresh cannot interleave between them.
     *
     * Non-suspend (UI entry point, like [enrichVisibleItems]): [stateMutex] is not
     * reentrant and cannot be taken from a non-suspending context, so the work is handed to
     * this DirState's own scope.
     *
     * Named `sortBy` rather than `setSortKey` because a property setter with that exact
     * signature would clash on the JVM.
     */
    fun sortBy(key: SortKey) {
        if (isDestroyed.get()) return
        if (key == sortKey && _baseDirectory.size > 0) return
        sortKey = key
        if (_baseDirectory.size == 0) return
        scope.launch(ioDispatcher) {
            stateMutex.withLock {
                _baseDirectory.sortWith(FileEntry.comparatorFor(key))
                rebuildComposite()
            }
        }
    }

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

    private suspend fun flushEnrichmentBatch(batch: List<FileEntry>) {
        stateMutex.withLock {
            val current = _deltas.value
            val newEnrichments = current.enrichments + batch.filterIsInstance<FileInfo>().associateBy { it.uri }
            _deltas.value = current.copy(enrichments = newEnrichments)
            rebuildComposite()
        }
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
        // Claim a new loading generation BEFORE launching: the old job's `finally`
        // runs while we join it below and must already see itself as superseded.
        val epoch = loadEpoch.incrementAndGet()
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

                // Clear deltas. The listing is NOT emitted here: the single emission for this
                // refresh is the rebuildComposite() at the end of the lock block below, which
                // carries the enrichments queued by the enrichItemLocked loop. Publishing an
                // empty-delta composite first (the old behaviour) made every refresh emit twice
                // — the second emission being the one the UI actually cared about.
                stateMutex.withLock {
                    _baseDirectory = dir
                    _deltas.value = DeltaState()

                    // Trace marks only — they no longer bracket an emission point; the emission
                    // this used to time now happens at the trailing rebuildComposite().
                    timer?.mark("first_chunk_rendered", itemCount = dir.size)
                    timer?.mark("dir_list_done", itemCount = dir.size)

                    // Update cache
                    fileCache.clear()
                    for (i in 0 until dir.size) {
                        fileCache[dir.getUri(i)] = dir.get(i)
                    }

                    // Enrichment AFTER listing — already inside stateMutex, so use the
                    // locked variant and rebuild once after the loop
                    for (info in enrichable) {
                        enrichItemLocked(info)
                    }
                    rebuildComposite()
                }
            } catch (e: Exception) {
                // Fail-soft: a superseded job must not publish its error over a newer load.
                if (e !is kotlinx.coroutines.CancellationException && epoch == loadEpoch.get()) {
                    _loadError.value = e
                }
            } finally {
                if (epoch == loadEpoch.get()) _isLoading.value = false
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

        // Update delta layer atomically — synchronize with refresh/onActive
        stateMutex.withLock {
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
        }

        fetchedInfos.forEach { enrichItem(it) }
    }

    /** Returns [info] with its emblems applied, or null when there are none to record. */
    private fun applyEmblems(info: FileInfo): FileInfo? {
        val emblems = mutableListOf<String>()
        if (info.isSymlink) emblems.add("emblem-symbolic-link")
        if (!info.isWritable) emblems.add("emblem-readonly")
        val customEmblems = info.attributes["metadata::emblems"] as? List<*>
        customEmblems?.filterIsInstance<String>()?.let { emblems.addAll(it) }
        if (emblems.isEmpty()) return null
        return info.copy(attributes = info.attributes + mapOf("std::emblems" to emblems))
    }

    /**
     * Records emblems into the enrichment delta and queues the item for the async
     * enrichment workers.
     *
     * The read-modify-write of [_deltas] runs under [stateMutex]: it races with
     * flushEnrichmentBatch, handleEventBatch and the refresh/onActive rebases, which
     * would otherwise silently drop another writer's additions/deletions.
     */
    private suspend fun enrichItem(info: FileInfo, rebuild: Boolean = true) {
        if (!enrichedUris.add(info.uri)) return
        val enriched = applyEmblems(info)
        if (enriched != null) {
            stateMutex.withLock {
                val current = _deltas.value
                _deltas.value = current.copy(enrichments = current.enrichments + (enriched.uri to enriched))
                if (rebuild) rebuildComposite()
            }
        }
        enrichmentChannel.trySend(enriched ?: info)
    }

    /**
     * [enrichItem] for callers that already hold [stateMutex] — the mutex is not
     * reentrant, so it must not be taken again here. Never rebuilds: the caller
     * rebuilds once after its loop.
     */
    private fun enrichItemLocked(info: FileInfo) {
        if (!enrichedUris.add(info.uri)) return
        val enriched = applyEmblems(info)
        if (enriched != null) {
            val current = _deltas.value
            _deltas.value = current.copy(enrichments = current.enrichments + (enriched.uri to enriched))
        }
        enrichmentChannel.trySend(enriched ?: info)
    }

    /**
     * Viewport-driven enrichment: only enrich items visible in the viewport.
     * Called by the UI when the visible items change (scroll, resize).
     *
     * Not a suspend function (UI entry point): the delta writes are mutex-guarded, so
     * the batch is handed to this DirState's scope instead of blocking the caller.
     */
    fun enrichVisibleItems(visibleUris: List<String>) {
        // Collect under the mutex inside the coroutine: point-reads of fileCache/
        // _baseDirectory race with refresh/onActive's under-lock mutations (plain
        // LinkedHashMap — a structural read during clear()/put is undefined).
        // Application then runs outside the lock (enrichItem takes it per call).
        scope.launch {
            val pending = stateMutex.withLock {
                val deltas = _deltas.value
                val collected = mutableListOf<FileInfo>()
                visibleUris.forEach { uri ->
                    if (enrichedUris.contains(uri)) return@forEach
                    // Check additions/enrichments first (these are FileInfo objects)
                    val deltaEntry = deltas.additions[uri] ?: deltas.enrichments[uri]
                    if (deltaEntry != null) {
                        if (!deltaEntry.isDirectory) collected.add(deltaEntry)
                        return@forEach
                    }
                    // For base directory entries, look up the original FileInfo from fileCache
                    val idx = _baseDirectory.findIndex(uri)
                    if (idx == -1) return@forEach
                    val cached = fileCache[uri]
                    if (cached is FileInfo && !cached.isDirectory) {
                        collected.add(cached)
                    }
                }
                collected
            }
            for (info in pending) enrichItem(info)
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
        // Shares the generation counter with refresh(): both paths own the spinner and
        // both replace refreshJob, so a revalidate superseded by a later refresh (or vice
        // versa) must not clear _isLoading while the newer one is still working.
        val epoch = loadEpoch.incrementAndGet()
        // A warm revalidate (cached listing already present) must not flash the spinner:
        // the listing only swaps if the changed-check below finds something different.
        // First load (empty listing) keeps the original loading-flag behaviour.
        val isWarmRevalidate = _baseDirectory.size > 0
        if (!isWarmRevalidate) _isLoading.value = true
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

                // Compare with current base (quick size + content check).
                // modifiedTime must be part of the fingerprint: an in-place edit that keeps
                // the byte count identical (configs, logs, source files) is otherwise invisible
                // and the listing would stay stale until an external watch event arrives.
                val current = _baseDirectory
                var changed = dir.size != current.size
                if (!changed) {
                    for (i in 0 until dir.size) {
                        val next = dir.get(i)
                        val prev = current.get(i)
                        if (dir.getUri(i) != current.getUri(i) ||
                            next.size != prev.size ||
                            next.modifiedTime != prev.modifiedTime ||
                            next.isDirectory != prev.isDirectory ||
                            next.mimeType != prev.mimeType
                        ) {
                            changed = true
                            break
                        }
                    }
                }

                if (changed) {
                    // Same single-emission rule as refresh(): no empty-delta composite is
                    // published on adoption; the trailing rebuildComposite() is the emission.
                    stateMutex.withLock {
                        _baseDirectory = dir
                        _deltas.value = DeltaState()

                        // Rebuild the cache from the NEW listing. The cached entries are
                        // ArrayBackedEntry wrappers bound to the listing that produced them —
                        // leaving the old ones would resolve indices against the previous
                        // directory's parallel arrays (stale metadata) and keep it reachable.
                        fileCache.clear()
                        for (i in 0 until dir.size) {
                            fileCache[dir.getUri(i)] = dir.get(i)
                        }

                        for (info in enrichable) {
                            enrichItemLocked(info)
                        }
                        rebuildComposite()
                    }
                }
                timer?.mark("dir_revalidate_done", detail = uri, itemCount = dir.size)
            } catch (e: Exception) {
                if (e !is CancellationException && epoch == loadEpoch.get()) {
                    _loadError.value = e
                }
            } finally {
                if (epoch == loadEpoch.get()) _isLoading.value = false
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
            // Retire any in-flight load generation so its finally block cannot resurrect
            // loading/error state after teardown.
            loadEpoch.incrementAndGet()
            job.cancel()
            _baseDirectory = ListingDirectory(0)
            _compositeView = null
            _deltas.value = DeltaState()
            // Not a composite, so not routed through publish(): the listing is being cleared,
            // not rebuilt. The revision is still bumped so observers of [revision] see the
            // teardown rather than a stale listing sitting at the previous count.
            _itemsList.value = emptyList()
            _revision.value = emissionRevision.incrementAndGet()
            _isLoading.value = false
            _loadError.value = null
            enrichedUris.clear()
        }
    }
}


