@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.provider

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.Locality
import com.imbric.core.models.FileInfo
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.Collections

/**
 * Live state of an opened directory.
 * Combines initial listing with real-time monitoring and asynchronous enrichment.
 */
class DirState(
    val uri: String,
    private val backend: IOBackend,
    private val scope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO
) {

    private val _items = MutableStateFlow<Map<String, FileInfo>>(emptyMap())
    private val _itemsList = MutableStateFlow<List<FileInfo>>(emptyList())
    
    /**
     * The current list of files in the directory.
     * Updates automatically as the file system changes.
     */
    val items: StateFlow<List<FileInfo>> = _itemsList.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading

    private val enrichedUris = Collections.synchronizedSet(mutableSetOf<String>())
    private var watchJob: Job? = null

    init {
        refresh()
        startWatching()
    }

    /**
     * Forces a full reload of the directory contents.
     */
    fun refresh() {
        scope.launch(ioDispatcher) {
            _isLoading.value = true
            _items.value = emptyMap()
            _itemsList.value = emptyList()
            enrichedUris.clear()
            try {
                backend.list(uri)
                    .chunked(50)
                    .collect { chunk ->
                        _items.update { current ->
                            val next = current + chunk.associateBy { it.uri }
                            _itemsList.value = next.values.toList()
                            next
                        }
                        // Start enrichment for this chunk
                        chunk.forEach { enrichItem(it) }
                        
                        yield()
                    }
            } finally {
                _isLoading.value = false
            }
        }
    }

    private fun startWatching() {
        watchJob?.cancel()
        watchJob = scope.launch(ioDispatcher) {
            backend.watch(uri)
                .buffer()
                .collect { event ->
                    handleEvent(event)
                }
        }
    }

    private suspend fun handleEvent(event: FileEvent) {
        when (event) {
            is FileEvent.Created -> {
                backend.getMetadata(event.uri).onSuccess { info ->
                    updateItem(event.uri, info)
                    enrichItem(info)
                }
            }
            is FileEvent.Deleted -> {
                removeItem(event.uri)
                enrichedUris.remove(event.uri)
            }
            is FileEvent.Modified -> {
                backend.getMetadata(event.uri).onSuccess { info ->
                    updateItem(event.uri, info)
                    // Re-enrich on modification
                    enrichedUris.remove(event.uri)
                    enrichItem(info)
                }
            }
            is FileEvent.Renamed -> {
                _items.update { current ->
                    val next = current - event.from
                    _itemsList.value = next.values.toList()
                    next
                }
                enrichedUris.remove(event.from)
                backend.getMetadata(event.to).onSuccess { info ->
                    updateItem(event.to, info)
                    enrichItem(info)
                }
            }
        }
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
                    // Future: recursive count logic
                }
            }
        }
    }

    private fun updateItem(uri: String, info: FileInfo) {
        _items.update { current ->
            val next = current + (uri to info)
            _itemsList.value = next.values.toList()
            next
        }
    }

    private fun removeItem(uri: String) {
        _items.update { current ->
            val next = current - uri
            _itemsList.value = next.values.toList()
            next
        }
    }

    fun stop() {
        watchJob?.cancel()
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
