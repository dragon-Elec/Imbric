package com.imbric.core.ifs.provider

import com.imbric.core.desktop.StarredManager
import com.imbric.core.models.*
import com.imbric.core.models.SortKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.flow

/**
 * Defines how a [DirState] obtains its initial file listing.
 *
 * This replaces Nautilus's directory subclassing pattern
 * (NautilusSearchDirectory, NautilusVfsDirectory, etc.)
 * with composable data classes instead of class inheritance.
 *
 * Each strategy defines a [list] method that produces a [Flow] of [FileInfo].
 * The [DirState] collects this flow in [DirState.refresh] and populates its state.
 */
sealed interface ListingStrategy {

    /**
     * Lists files using the backend's [com.imbric.core.ifs.IOBackend.list] method.
     * This is the default strategy for normal directory browsing.
     */
    data object Standard : ListingStrategy {
        override fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): Flow<FileEntry> =
            backend.list(uri, sortKey)

        override fun watchable(): Boolean = true
    }

    /**
     * Lists files using the backend's [com.imbric.core.ifs.IOBackend.search] method.
     * Used for search result directories where the content is defined by a query.
     */
    data class Search(val query: VfsQuery) : ListingStrategy {
        override fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): Flow<FileEntry> =
            backend.search(query)

        override fun watchable(): Boolean = false // Search results don't have a real directory to watch
    }

    /**
     * Lists starred files by subscribing to [StarredManager.starredUris]
     * and fetching metadata for each URI.
     *
     * This is the Kotlin equivalent of Nautilus's NautilusSearchDirectory
     * for the "Starred" view.
     */
    data class Starred(val starredManager: StarredManager) : ListingStrategy {
        override fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): Flow<FileEntry> = flow {
            val uris = starredManager.starredUris.value
            if (uris.isNotEmpty()) {
                val results = backend.getMetadata(uris.toList())
                results.forEach { result ->
                    result.getOrNull()?.let { emit(it) }
                }
            }
        }

        override fun watchable(): Boolean = false // Starred set changes via StarredManager, not GIO monitoring
    }

    /**
     * Provides a static list of items. Used for virtual directories
     * like bookmarks, network shares, or custom aggregations.
     */
    data class Virtual(val items: List<FileEntry>) : ListingStrategy {
        override fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): Flow<FileEntry> = flow {
            items.forEach { emit(it) }
        }

        override fun watchable(): Boolean = false // Virtual directories have no real filesystem to watch
    }

    /**
     * Produces a [Flow] of [FileInfo] for the initial directory listing.
     * Called by [DirState.refresh] to populate the directory contents.
     */
    fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey = SortKey.NAME): Flow<FileEntry>

    /**
     * Returns true if this strategy supports real-time file monitoring.
     * Strategies that return false will not start a GIO file monitor.
     */
    fun watchable(): Boolean
}
