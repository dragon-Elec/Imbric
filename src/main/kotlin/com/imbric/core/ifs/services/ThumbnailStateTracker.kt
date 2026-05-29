package com.imbric.core.ifs.services

import com.imbric.core.models.*
import com.imbric.core.ifs.IOBackend
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.concurrent.ConcurrentHashMap

/**
 * State coordinator for thumbnail generation.
 * Wraps [IOBackend.getThumbnailPath] and [IOBackend.generateThumbnail]
 * and tracks loading/failed state for UI observation.
 *
 * This is a SERVICE — it has state the UI observes. It is NOT a backend capability.
 * The actual thumbnail operations live on [IOBackend].
 *
 * Ported from nautilus-thumbnails.c state tracking logic.
 */
class ThumbnailStateTracker(
    private val backend: IOBackend,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    private val MAX_THUMBNAIL_SIZE = 10 * 1024 * 1024 // 10MB limit for local files

    /** URIs currently being thumbnailed. UI observes this for loading spinners. */
    private val _thumbnailingInProgress = MutableStateFlow<Set<String>>(emptySet())
    val thumbnailingInProgress: StateFlow<Set<String>> = _thumbnailingInProgress.asStateFlow()

    /** URIs that failed thumbnail generation. UI observes this for error states. */
    private val _thumbnailingFailed = MutableStateFlow<Set<String>>(emptySet())
    val thumbnailingFailed: StateFlow<Set<String>> = _thumbnailingFailed.asStateFlow()

    /**
     * Returns true if the given file can be thumbnailed.
     */
    fun canThumbnail(info: FileInfo): Boolean {
        if (info.isDirectory) return false
        if (info.size > MAX_THUMBNAIL_SIZE) return false
        
        val mime = info.mimeType.lowercase()
        return mime.startsWith("image/") || 
               mime.startsWith("video/") || 
               mime == "application/pdf" ||
               mime.endsWith("/webp") ||
               mime.endsWith("/heic")
    }

    /**
     * Checks if a specific URI is currently being thumbnailed.
     */
    fun isCurrentlyThumbnailing(uri: String): Boolean = uri in _thumbnailingInProgress.value

    /**
     * Checks if thumbnail generation failed for a specific URI.
     */
    fun hasFailed(uri: String): Boolean = uri in _thumbnailingFailed.value

    /**
     * Ensures a thumbnail exists for the given file.
     * First checks the backend for an existing thumbnail path,
     * then triggers generation if needed.
     *
     * Automatically tracks state: marks the URI as in-progress,
     * and clears or sets the failed flag on completion.
     */
    suspend fun ensureThumbnail(info: FileInfo): String? {
        if (!canThumbnail(info)) return null
        
        val uri = info.uri
        
        // Fast path: backend already has a thumbnail
        val existingPath = backend.getThumbnailPath(uri)
        if (existingPath != null) return existingPath

        // Need to generate — track state
        markInProgress(uri)
        
        return try {
            val result = backend.generateThumbnail(uri)
            if (result.isSuccess) {
                val path = result.getOrNull()
                if (path != null) {
                    markComplete(uri)
                } else {
                    // Not supported by backend, but not a "failure"
                    _thumbnailingInProgress.update { it - uri }
                }
                path
            } else {
                markFailed(uri)
                null
            }
        } catch (e: Exception) {
            markFailed(uri)
            null
        }
    }

    private fun markInProgress(uri: String) {
        _thumbnailingInProgress.update { it + uri }
        _thumbnailingFailed.update { it - uri }
    }

    private fun markComplete(uri: String) {
        _thumbnailingInProgress.update { it - uri }
        _thumbnailingFailed.update { it - uri }
    }

    private fun markFailed(uri: String) {
        _thumbnailingInProgress.update { it - uri }
        _thumbnailingFailed.update { it + uri }
    }

    /**
     * Clears the failed state for a URI, allowing retry.
     */
    fun clearFailedState(uri: String) {
        _thumbnailingFailed.update { it - uri }
    }

    /**
     * Clears all thumbnailing state. Useful on directory refresh.
     */
    fun clearAllState() {
        _thumbnailingInProgress.value = emptySet()
        _thumbnailingFailed.value = emptySet()
    }
}
