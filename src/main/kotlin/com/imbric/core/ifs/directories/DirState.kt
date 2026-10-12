@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.directories

import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.ListingDispatchers
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.backends.gio.support.PipelineTimer

import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.delay
import kotlin.coroutines.EmptyCoroutineContext
import java.util.Collections
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * Live state of an opened directory.
 * Combines initial listing with real-time monitoring and emblem enrichment.
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
     * refresh/onActive/handleEventBatch/enrichItem. It also
     * guards the read paths that walk the installed listing (refresh's dedup
     * pass, onActive's change compare, containsFile): sortBy mutates
     * _baseDirectory in place under this lock, so an unsynchronized reader
     * can observe a half-applied permutation.
     * Not reentrant — never call a suspending helper that takes it again from inside a
     * `withLock` block.
     */
    private val stateMutex = Mutex()
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
     * enrichItem) and from sortBy's lock block — the reads of
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
     * where base, deltas and comparator are read as a consistent triple). The comparator
     * is passed in rather than read from [sortKey] so the caller controls exactly which
     * ordering the published view advertises.
     */
    private fun rebuildComposite(comparator: Comparator<FileEntry>) {
        val base = _baseDirectory
        val deltas = _deltas.value
        // Create a NEW immutable view on every rebuild — identity equality forces StateFlow emission
        val composite = EnrichedListingView(
            base = base,
            comparator = comparator,
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
    /**
     * Held in AtomicReferences rather than plain vars: [startWatching]/[refresh]/[onActive]
     * install these from the Listing dispatcher while [stop]/[destroy] clear them from the
     * UI thread. With a plain var the cancel-then-assign pair is a read-modify-write that two
     * threads can interleave, orphaning a watcher Job whose `awaitClose` (and the
     * GIO `monitor.cancel()` behind it) then never runs. getAndSet makes the swap-and-cancel
     * atomic at every install site.
     */
    private val watchJob = AtomicReference<Job?>(null)
    private val refreshJob = AtomicReference<Job?>(null)
    /**
     * Idle CPU telemetry loop, when tracing is on. Held so a newer load can cancel a
     * predecessor's loop deterministically (the epoch check would retire it on its own,
     * but only at the next tick) and so [destroy] can drop it explicitly.
     */
    private val idleCpuJob = AtomicReference<Job?>(null)
    private val isDestroyed = AtomicBoolean(false)
    /** True if [destroy] has been called. The registry uses this to detect stale entries. */
    val isDestroyedState: Boolean get() = isDestroyed.get()

    /** The current sort key. Set through [sortBy]; DirState adapts attribute fetching. Volatile: read on the UI thread in [sortBy]'s guard, written under [stateMutex] on IO. */
    @Volatile
    private var sortKey: SortKey = SortKey.NAME

    /**
     * Changes the sort key and re-sorts the loaded listing — no re-list,
     * [FileEntry.listingAttributesFor] already fetches the columns every key needs.
     *
     * Non-suspend (UI entry point): [stateMutex] is not reentrant, so the sort +
     * [rebuildComposite] run in this instance's own scope under one lock.
     */
    fun sortBy(key: SortKey) {
        if (isDestroyed.get()) return
        // TYPE's comparator falls back to SortByName, so TYPE and NAME can share one
        // comparator — the identity check inside the lock skips the physical sort while
        // still publishing the rebuilt view.
        if (key == sortKey && _baseDirectory.size > 0) return
        // Empty listing: just record the key; the next refresh/onActive installs
        // rows already sorted by it.
        if (_baseDirectory.size == 0) {
            scope.launch(ioDispatcher) {
                stateMutex.withLock {
                    if (isDestroyed.get()) return@withLock
                    sortKey = key
                }
            }
            return
        }
        scope.launch(ioDispatcher) {
            stateMutex.withLock {
                if (isDestroyed.get()) return@withLock
                val oldC = FileEntry.comparatorFor(sortKey)
                sortKey = key
                val newC = FileEntry.comparatorFor(key)
                if (newC !== oldC) _baseDirectory.sortWith(newC)
                rebuildComposite(newC)
            }
        }
    }

    private val fileCache = LinkedHashMap<String, FileEntry>(512)

    init {
        refresh() // refresh() calls startWatching() internally
    }

    /**
     * Re-loads the directory contents and updates the cache.
     * Cancels any in-progress refresh to prevent interleaved data.
     * Restarts monitoring if it was stopped.
     */
    fun refresh() {
        if (isDestroyed.get()) return
        val oldJob = refreshJob.get()
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
                // Unchanged-row dedup: fileCache is lazily populated (only rows
                // actually read are materialized), so it can no longer answer this
                // check. The previous listing is still installed at this point
                // (_baseDirectory is swapped inside the lock below), so the old row
                // is read straight from its URI index — O(1) — and the transient
                // wrapper is discarded once the comparison is done instead of being
                // retained in the cache.
                //
                // The old-row reads happen under stateMutex: sortBy mutates the
                // installed listing in place (sortWith → applyPermutation +
                // buildUriIndex) under the same lock, so an unlocked findIndex/get
                // could observe a half-applied permutation. Same shape as
                // enrichVisibleItems: collect the decisions inside the lock, then
                // apply them to the local directory outside it.
                val deduped = stateMutex.withLock {
                    if (isDestroyed.get()) return@withLock emptyList<FileEntry>()
                    val decisions = ArrayList<FileEntry>(allItems.size)
                    for (item in allItems) {
                        val oldIndex = _baseDirectory.findIndex(item.uri)
                        val cached = if (oldIndex != -1) _baseDirectory.get(oldIndex) else null
                        decisions.add(
                            if (cached != null && cached.modifiedTime == item.modifiedTime && cached.size == item.size) {
                                cached
                            } else {
                                item
                            }
                        )
                    }
                    decisions
                }
                for (itemToStore in deduped) {
                    dir.add(itemToStore)
                }
                dir.sortWith(FileEntry.comparatorFor(sortKey))

                // Clear deltas. The listing is NOT emitted here: the single emission for this
                // refresh is the rebuildComposite() at the end of the lock block below,
                // which carries the current delta state. Publishing an
                // empty-delta composite first (the old behaviour) made every refresh emit twice
                // — the second emission being the one the UI actually cared about.
                stateMutex.withLock {
                    if (isDestroyed.get()) return@withLock
                    _baseDirectory = dir
                    _deltas.value = DeltaState()

                    // Trace marks only — they no longer bracket an emission point; the emission
                    // this used to time now happens at the trailing rebuildComposite().
                    timer?.mark("first_chunk_rendered", itemCount = dir.size)
                    timer?.mark("dir_list_done", itemCount = dir.size)

                    // Drop wrappers bound to the replaced listing: they would
                    // resolve indices against the old parallel arrays and keep
                    // that directory reachable. The cache is NOT repopulated —
                    // rows materialize on demand via getOrPut (see
                    // enrichVisibleItems), so only rows actually read ever
                    // become objects.
                    fileCache.clear()

                    rebuildComposite(FileEntry.comparatorFor(sortKey))
                }
            } catch (e: Exception) {
                // Fail-soft: a superseded job must not publish its error over a newer load.
                if (e !is kotlinx.coroutines.CancellationException && epoch == loadEpoch.get()) {
                    _loadError.value = e
                }
            } finally {
                if (epoch == loadEpoch.get()) {
                    _isLoading.value = false
                    // Only the load that still owns the spinner may declare the instance idle.
                    startIdleCpuSampling(timer, epoch)
                }
                timer?.mark("dir_refresh_done", itemCount = _baseDirectory.size)
            }
        }
        refreshJob.getAndSet(newJob)?.cancel()
    }

    /**
     * Starts the idle CPU sampler for [timer] if this instance has just gone idle at
     * [epoch], replacing any loop a previous load left behind.
     * [isStillIdle] is the epoch comparison: refresh/onActive claim the next
     * [loadEpoch] before launching, so the loop retires itself when a new load starts.
     */
    private fun startIdleCpuSampling(timer: PipelineTimer?, epoch: Long) {
        if (timer == null) return
        if (isDestroyed.get()) return
        idleCpuJob.getAndSet(null)?.cancel()
        val sampler = IdleCpuSampler(
            timer = timer,
            isDestroyed = { isDestroyed.get() },
            isStillIdle = { epoch == loadEpoch.get() }
        )
        idleCpuJob.set(sampler.start(scope))
        // destroy() can land between the guard above and this set — re-check so a torn-down
        // instance never leaves a live Job reference behind.
        if (isDestroyed.get()) idleCpuJob.getAndSet(null)?.cancel()
    }

    private fun startWatching() {
        if (isDestroyed.get()) return
        if (!strategy.watchable()) return // Virtual/Search/Starred strategies don't watch
        // Cancel the current watcher first (preserves the previous cancel-before-start
        // ordering, so two consumers never run concurrently), then install atomically:
        // getAndSet also cancels anything a racing thread installed in between, so no
        // watcher Job can be orphaned.
        watchJob.get()?.cancel()
        val newWatchJob = scope.launch(ioDispatcher) {
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
        watchJob.getAndSet(newWatchJob)?.cancel()
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
            if (isDestroyed.get()) return@withLock
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
            rebuildComposite(FileEntry.comparatorFor(sortKey))
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
     * Applies emblems to [info] and records the result in the enrichment delta.
     * Synchronous and emblem-only: the async metadata pipeline is gone, so this
     * is the entire enrichment path for event-driven and viewport-driven items.
     *
     * The read-modify-write of [_deltas] runs under [stateMutex]: it races with
     * handleEventBatch and the refresh/onActive rebases, which would otherwise
     * silently drop another writer's additions/deletions.
     */
    private suspend fun enrichItem(info: FileInfo, rebuild: Boolean = true) {
        if (!enrichedUris.add(info.uri)) return
        val enriched = applyEmblems(info)
        if (enriched != null) {
            stateMutex.withLock {
                val current = _deltas.value
                _deltas.value = current.copy(enrichments = current.enrichments + (enriched.uri to enriched))
                if (rebuild) rebuildComposite(FileEntry.comparatorFor(sortKey))
            }
        }
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
                    // For base directory entries, materialize the row on demand.
                    // getOrPut is the contract here: after the lazy-cache change the
                    // lookup must still find the entry, creating the wrapper (bound
                    // to the current listing) only when actually read.
                    val idx = _baseDirectory.findIndex(uri)
                    if (idx == -1) return@forEach
                    val entry = fileCache.getOrPut(uri) { _baseDirectory.get(idx) }
                    if (entry.isDirectory) return@forEach
                    // Base rows are ArrayBackedEntry/ListingFile post-flatten on all
                    // backends. FileEntry carries isSymlink, so the overlay is exact
                    // for links; isWritable/attributes are FileInfo-only, so synthesized
                    // rows default writable + empty attributes (never lie about readonly).
                    val info = entry as? FileInfo ?: FileInfo(
                        name = entry.name, path = entry.path, uri = entry.uri,
                        pathType = entry.pathType, isDirectory = false,
                        isSymlink = entry.isSymlink, size = entry.size,
                        mimeType = entry.mimeType, modifiedTime = entry.modifiedTime,
                        isHidden = entry.isHidden, iconName = entry.iconName,
                        isInTrash = entry.isInTrash, isInRecent = entry.isInRecent,
                        isRemote = entry.isRemote,
                    )
                    collected.add(info)
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

    /**
     * Returns true if the directory contains a file with the given URI.
     *
     * Suspend (like [enrichItem]): the final lookup walks the installed
     * listing's uriIndex, which sortBy rebuilds in place under [stateMutex],
     * so the whole check runs inside the lock. The [StateFlow] reads are
     * atomic on their own, but they stay inside for a single consistent
     * answer against the base directory.
     *
     * Never call this from inside a [stateMutex.withLock] block: the
     * mutex is non-reentrant, so a nested [containsFile] would deadlock
     * the caller against itself.
     */
    suspend fun containsFile(uri: String): Boolean = stateMutex.withLock {
        val deltas = _deltas.value
        when {
            uri in deltas.deletions -> false
            uri in deltas.additions -> true
            else -> _baseDirectory.containsUri(uri)
        }
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

    // --- Lifecycle ---

    /**
     * Called when this DirState becomes actively viewed by the UI.
     * Restarts monitoring and triggers a background check/sync without clearing current items or showing the spinner.
     */
    fun onActive() {
        if (isDestroyed.get()) return
        startWatching()
        if (_isLoading.value) return

        val oldJob = refreshJob.get()
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
                fetched.forEach {
                    dir.add(it)
                }
                dir.sortWith(FileEntry.comparatorFor(sortKey))

                // Compare with current base (quick size + content check).
                // modifiedTime must be part of the fingerprint: an in-place edit that keeps
                // the byte count identical (configs, logs, source files) is otherwise invisible
                // and the listing would stay stale until an external watch event arrives.
                // The compare reads the installed listing, so it runs under stateMutex
                // (same reason as refresh's dedup pass above): an unlocked read races
                // sortBy's in-place mutation of _baseDirectory. Only the compare is
                // collected here; the adoption swap below stays in its own lock block
                // — the mutex is not reentrant.
                val changed = stateMutex.withLock {
                    if (isDestroyed.get()) return@withLock false
                    val current = _baseDirectory
                    var changed = dir.size != current.size
                    if (!changed) {
                        for (i in 0 until dir.size) {
                            if (dir.getUri(i) != current.getUri(i) ||
                                dir.getSizeAt(i) != current.getSizeAt(i) ||
                                dir.getModifiedMillisAt(i) != current.getModifiedMillisAt(i) ||
                                dir.isDirAt(i) != current.isDirAt(i) ||
                                dir.getMimeAt(i) != current.getMimeAt(i)
                            ) {
                                changed = true
                                break
                            }
                        }
                    }
                    changed
                }

                if (changed) {
                    // Same single-emission rule as refresh(): no empty-delta composite is
                    // published on adoption; the trailing rebuildComposite() is the emission.
                    stateMutex.withLock {
                        if (isDestroyed.get()) return@withLock
                        _baseDirectory = dir
                        _deltas.value = DeltaState()

                        // Drop wrappers bound to the replaced listing: they would
                        // resolve indices against the previous directory's parallel
                        // arrays (stale metadata) and keep it reachable. The cache is
                        // NOT repopulated — rows materialize on demand via getOrPut
                        // (see enrichVisibleItems).
                        fileCache.clear()

                        rebuildComposite(FileEntry.comparatorFor(sortKey))
                    }
                }
                timer?.mark("dir_revalidate_done", detail = uri, itemCount = dir.size)
            } catch (e: Exception) {
                if (e !is CancellationException && epoch == loadEpoch.get()) {
                    _loadError.value = e
                }
            } finally {
                if (epoch == loadEpoch.get()) {
                    _isLoading.value = false
                    startIdleCpuSampling(timer, epoch)
                }
            }
        }
        refreshJob.getAndSet(newJob)?.cancel()
    }

    /**
     * Stops monitoring and enrichment, but keeps the current data in memory.
     * Use this when a view navigates away but you want fast re-open via [DirStateRegistry].
     * Call [refresh] to restart monitoring.
     */
    fun stop() {
        watchJob.getAndSet(null)?.cancel()
    }

    /** Clears listing/delta/cache and publishes the empty view. Caller must hold [stateMutex]. */
    private fun clearLocked() {
        if (!isDestroyed.get()) return
        _baseDirectory = ListingDirectory(0)
        _deltas.value = DeltaState()
        fileCache.clear()
        publish(emptyView)
    }

    /**
     * Empty composite published by [destroy] to clear the item list. Routed through
     * [publish] so the emission counter counts the teardown like any other emission.
     */
    private val emptyView = EnrichedListingView(
        base = ListingDirectory(0),
        comparator = FileEntry.comparatorFor(SortKey.NAME),
        additions = emptyMap(),
        deletions = emptySet(),
        enrichments = emptyMap()
    )

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
            // Cancelled explicitly as well as via the scope: the loop is a child of `scope`,
            // so `job.cancel()` already covers it, but the explicit cancel makes the
            // no-mark-after-teardown guarantee local to destroy() and keeps the reference
            // from outliving the instance.
            idleCpuJob.getAndSet(null)?.cancel()
            watchJob.getAndSet(null)?.cancel()
            refreshJob.getAndSet(null)?.cancel()
            _isLoading.value = false
            _loadError.value = null
            enrichedUris.clear()
            // Teardown races the locked writers: take stateMutex and route through
            // publish(). Fallback launches on parentScope — job.cancel() above killed
            // scope, so a launch into it never runs. NonCancellable covers teardown
            // racing a registry/window shutdown; the block is memory-only.
            if (stateMutex.tryLock()) {
                try {
                    clearLocked()
                } finally {
                    stateMutex.unlock()
                }
            } else {
                parentScope.launch(NonCancellable) {
                    stateMutex.withLock { clearLocked() }
                }
            }
        }
    }
}


