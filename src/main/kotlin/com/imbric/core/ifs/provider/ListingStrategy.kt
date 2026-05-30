package com.imbric.core.ifs.provider

import com.imbric.core.desktop.StarredManager
import com.imbric.core.models.*
import com.imbric.core.models.SortKey
import kotlinx.coroutines.flow.firstOrNull

/**
 * Defines how a [DirState] obtains its initial file listing.
 *
 * This replaces Nautilus's directory subclassing pattern
 * (NautilusSearchDirectory, NautilusVfsDirectory, etc.)
 * with composable data classes instead of class inheritance.
 *
 * Each strategy defines a [list] method that returns a [List] of [FileEntry].
 * The [DirState] calls this in [DirState.refresh] and populates its state.
 */
sealed interface ListingStrategy {

    /**
     * Lists files using the backend's [com.imbric.core.ifs.IOBackend.list] method.
     * This is the default strategy for normal directory browsing.
     */
    data object Standard : ListingStrategy {
        override suspend fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): List<FileEntry> =
            backend.list(uri, sortKey)

        override fun watchable(): Boolean = true
    }

    /**
     * Lists files using the backend's [com.imbric.core.ifs.IOBackend.search] method.
     * Used for search result directories where the content is defined by a query.
     */
    data class Search(val query: VfsQuery) : ListingStrategy {
        override suspend fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): List<FileEntry> =
            backend.search(query).firstOrNull() ?: emptyList()

        override fun watchable(): Boolean = false
    }

    /**
     * Lists starred files by subscribing to [StarredManager.starredUris]
     * and fetching metadata for each URI.
     */
    data class Starred(val starredManager: StarredManager) : ListingStrategy {
        override suspend fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): List<FileEntry> {
            val uris = starredManager.starredUris.value
            return if (uris.isNotEmpty()) {
                backend.getMetadata(uris.toList()).mapNotNull { it.getOrNull() }
            } else {
                emptyList()
            }
        }

        override fun watchable(): Boolean = false
    }

    /**
     * Provides a static list of items. Used for virtual directories
     * like bookmarks, network shares, or custom aggregations.
     */
    data class Virtual(val items: List<FileEntry>) : ListingStrategy {
        override suspend fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey): List<FileEntry> =
            items

        override fun watchable(): Boolean = false
    }

    /**
     * Returns the directory listing as a [List] of [FileEntry].
     * Called by [DirState.refresh] to populate the directory contents.
     */
    suspend fun list(backend: com.imbric.core.ifs.IOBackend, uri: String, sortKey: SortKey = SortKey.NAME): List<FileEntry>

    /**
     * Returns true if this strategy supports real-time file monitoring.
     * Strategies that return false will not start a GIO file monitor.
     */
    fun watchable(): Boolean
}
