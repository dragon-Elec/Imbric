package com.imbric.app.viewmodel

import com.imbric.app.ui.LayoutMode
import com.imbric.core.ifs.IfsUri
import com.imbric.core.ifs.backends.gio.support.PipelineTimer
import com.imbric.core.ifs.directories.DirState
import com.imbric.core.ifs.directories.DirStateRegistry
import com.imbric.core.models.FileEntry
import com.imbric.core.models.SortKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

/**
 * Atomic state representing the file browser's current view.
 * Prevents race conditions between [uri], [items], and [isLoading] during transitions.
 */
data class FileBrowserState(
    val uri: String,
    val virtualUri: String,
    val items: List<FileEntry> = emptyList(),
    /**
     * Monotonic counter bumped once per published composite emission from
     * [DirState]. The UI uses it as a stable "content changed" trigger, so a
     * re-sort that happens to produce an equal [items] list still invalidates
     * derived state, and consumers never have to walk the list comparing
     * `hashCode()` (O(n) per emission) to detect change.
     */
    val itemsRevision: Int = 0,
    val isLoading: Boolean = true,
    val canGoUp: Boolean = false,
    val canGoBack: Boolean = false,
    val canGoForward: Boolean = false,
    val forwardStack: List<String> = emptyList()
)

/**
 * ViewModel for the file browser.
 * Owns the [DirState] lifecycle — destroys the previous state when navigating away.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FileBrowserViewModel(
    private val registry: DirStateRegistry,
    initialUri: String,
    private val viewModelScope: CoroutineScope
) {
    private val _currentUri = MutableStateFlow(initialUri)
    val currentUri: StateFlow<String> = _currentUri.asStateFlow()

    private val _virtualUri = MutableStateFlow(initialUri)
    val virtualUri: StateFlow<String> = _virtualUri.asStateFlow()

    private val _backStack = MutableStateFlow<List<String>>(emptyList())
    private val _forwardStack = MutableStateFlow<List<String>>(emptyList())

    private val _layoutMode = MutableStateFlow(LayoutMode.GRID)
    val layoutMode: StateFlow<LayoutMode> = _layoutMode.asStateFlow()

    private val _sortKey = MutableStateFlow(SortKey.NAME)
    val sortKey: StateFlow<SortKey> = _sortKey.asStateFlow()

    /** Optional pipeline timer. Set to non-null to enable timing traces. */
    var pipelineTimer: PipelineTimer? = null
        set(value) {
            field = value
            registry.pipelineTimer = value
        }

    /**
     * URI whose [DirState] this viewer currently holds a pin on, or null if none.
     * The pin blocks LRU eviction for as long as this pane displays the URI.
     */
    @Volatile
    private var pinnedUri: String? = null

    /**
     * Returns the [DirState] for [uri], holding a viewer pin on it. When [uri]
     * differs from the previously pinned URI, the old pin is dropped first
     * (the viewer navigated away — the instance stays cached for instant return,
     * but becomes an eviction candidate again).
     *
     * The equality guard matters because [dirStateFlow] is seeded with an initial
     * value that the first upstream emission would otherwise pin a second time.
     */
    private fun pinDirState(uri: String): DirState {
        val previouslyPinned = pinnedUri
        if (previouslyPinned == uri) return registry.getOrCreate(uri)
        if (previouslyPinned != null) registry.unpin(previouslyPinned)
        pinnedUri = uri
        return registry.pin(uri)
    }

    /**
     * Drops this viewer's pin on whatever URI is actually pinned (may lag
     * [_currentUri] if a navigation emission hasn't been collected yet) and
     * destroys the DirState if no other viewer holds it. Idempotent.
     */
    fun releasePin() {
        val uri = pinnedUri ?: return
        pinnedUri = null
        registry.release(uri)
    }

    private val dirStateFlow = _currentUri.map { uri ->
        val dirState = pinDirState(uri)
        dirState.onActive()
        dirState
    }.stateIn(
        viewModelScope,
        SharingStarted.Eagerly,
        pinDirState(initialUri).apply { onActive() }
    )

    /**
     * Single, atomic StateFlow of the complete browser UI state.
     * Combining them prevents a race condition where the path segment updates
     * before the file list flow switches, which previously caused a momentary
     * flash of "Empty Folder" for folders that actually contained files.
     */
    val state: StateFlow<FileBrowserState> = dirStateFlow.flatMapLatest { dirState ->
        // The listing and its revision travel together as one pair. `combine` only
        // has typed overloads up to five flows, and the revision has to stay paired
        // with `items` anyway — a re-sort that reorders without changing content must
        // land in the same emission as the reordered list.
        val content = combine(dirState.items, dirState.revision) { items, revision ->
            items to revision
        }
        combine(
            content,
            dirState.isLoading,
            _backStack,
            _forwardStack,
            _virtualUri
        ) { listing, isLoading, back, forward, virtual ->
            FileBrowserState(
                uri = dirState.uri,
                virtualUri = virtual,
                items = listing.first,
                itemsRevision = listing.second,
                isLoading = isLoading,
                canGoUp = !IfsUri(dirState.uri).isRootUri(),
                canGoBack = back.isNotEmpty(),
                canGoForward = forward.isNotEmpty(),
                forwardStack = forward
            )
        }
    }.stateIn(
        viewModelScope,
        SharingStarted.Eagerly,
        FileBrowserState(
            uri = initialUri,
            virtualUri = initialUri,
            items = registry.getOrCreate(initialUri).items.value,
            isLoading = registry.getOrCreate(initialUri).isLoading.value,
            canGoUp = !IfsUri(initialUri).isRootUri()
        )
    )

    fun navigateTo(uri: String) {
        val oldUri = _currentUri.value
        if (oldUri != uri) {
            pipelineTimer?.mark("vm_navigate_to", detail = uri)
            registry.getOrCreate(oldUri).stop()
            _backStack.update { it + oldUri }
            _forwardStack.value = emptyList()
            
            if (!isParentOrSelf(uri, _virtualUri.value)) {
                _virtualUri.value = uri
            }
            
            _currentUri.value = uri
        }
    }

    fun goBack() {
        val back = _backStack.value
        if (back.isNotEmpty()) {
            val oldUri = _currentUri.value
            val targetUri = back.last()
            registry.getOrCreate(oldUri).stop()
            _backStack.value = back.dropLast(1)
            _forwardStack.update { listOf(oldUri) + it }
            
            if (!isParentOrSelf(targetUri, _virtualUri.value)) {
                _virtualUri.value = targetUri
            }
            
            _currentUri.value = targetUri
        }
    }

    fun goForward() {
        val forward = _forwardStack.value
        if (forward.isNotEmpty()) {
            val oldUri = _currentUri.value
            val targetUri = forward.first()
            registry.getOrCreate(oldUri).stop()
            _forwardStack.value = forward.drop(1)
            _backStack.update { it + oldUri }
            
            if (!isParentOrSelf(targetUri, _virtualUri.value)) {
                _virtualUri.value = targetUri
            }
            
            _currentUri.value = targetUri
        }
    }

    fun goUp() {
        val current = _currentUri.value
        val parent = IfsUri(current).parent
        if (parent.uriString == current) return
        navigateTo(parent.uriString)
    }

    fun toggleLayoutMode() {
        _layoutMode.value = if (_layoutMode.value == LayoutMode.LIST) LayoutMode.GRID else LayoutMode.LIST
    }

    fun setSortKey(key: SortKey) {
        _sortKey.value = key
        // Re-sort the existing listing in place — no re-list, no re-scan.
    // DirState publishes the reordered items (and a bumped revision), which
    // flows through `state` on its own.
    dirStateFlow.value.sortBy(key)
    }

    /**
     * Viewport-driven enrichment: only enrich items visible in the viewport.
     * Called by the UI when the visible items change (scroll, resize).
     */
    fun enrichVisibleItems(visibleUris: List<String>) {
        dirStateFlow.value.enrichVisibleItems(visibleUris)
    }
}

private fun isParentOrSelf(parent: String, child: String): Boolean {
    if (!child.startsWith(parent)) return false
    if (child.length == parent.length) return true
    if (parent.endsWith('/')) return true
    val nextChar = child.getOrNull(parent.length)
    return nextChar == '/'
}
