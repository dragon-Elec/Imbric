package com.imbric.app.viewmodel

import com.imbric.app.ui.LayoutMode
import com.imbric.core.ifs.IfsUri
import com.imbric.core.ifs.backends.PipelineTimer
import com.imbric.core.ifs.provider.DirState
import com.imbric.core.ifs.provider.DirStateRegistry
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

    private val dirStateFlow = _currentUri.map { uri ->
        val dirState = registry.getOrCreate(uri)
        dirState.onActive()
        dirState
    }.stateIn(
        viewModelScope,
        SharingStarted.Eagerly,
        registry.getOrCreate(initialUri).apply { onActive() }
    )

    /**
     * Single, atomic StateFlow of the complete browser UI state.
     * Combining them prevents a race condition where the path segment updates
     * before the file list flow switches, which previously caused a momentary
     * flash of "Empty Folder" for folders that actually contained files.
     */
    val state: StateFlow<FileBrowserState> = dirStateFlow.flatMapLatest { dirState ->
        combine(
            dirState.items,
            dirState.isLoading,
            _backStack,
            _forwardStack,
            _virtualUri
        ) { items, isLoading, back, forward, virtual ->
            FileBrowserState(
                uri = dirState.uri,
                virtualUri = virtual,
                items = items,
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
        // Update DirState's sort key so it fetches the right attributes on next refresh
        dirStateFlow.value.sortKey = key
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
