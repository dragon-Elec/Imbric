package com.imbric.core.ifs.services

import com.imbric.core.models.FileInfo
import com.imbric.core.ifs.backends.GioCoroutineBridge
import kotlinx.coroutines.*
import org.gnome.gio.*
import org.gnome.glib.GLib

/**
 * A service for asynchronous thumbnail generation and cache management.
 * Ported from nautilus-thumbnails.c.
 */
class ThumbnailService(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    private val MAX_THUMBNAIL_SIZE = 10 * 1024 * 1024 // 10MB limit for local files

    /**
     * Returns true if the given file can be thumbnailed.
     */
    fun canThumbnail(info: FileInfo): Boolean {
        if (info.isDirectory) return false
        
        // Don't thumbnail very large files to avoid OOM/Lag
        if (info.size > MAX_THUMBNAIL_SIZE) return false
        
        val mime = info.mimeType.lowercase()
        return mime.startsWith("image/") || 
               mime.startsWith("video/") || 
               mime == "application/pdf" ||
               mime.endsWith("/webp") ||
               mime.endsWith("/heic")
    }

    /**
     * Asynchronously ensures a thumbnail exists for the given file.
     * Returns the path to the thumbnail file in the local cache.
     */
    suspend fun getThumbnailPath(info: FileInfo): String? {
        if (!canThumbnail(info)) return null
        
        // If GIO already provided a thumbnail path, use it
        info.thumbnailPath?.let { return it }

        return try {
            val gfile = File.newForUri(info.uri)
            
            // We use the native GIO attribute query to trigger thumbnailing
            // if the backend supports it (like GIO's local backend).
            val updatedInfo = GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.queryInfoAsync(
                        "thumbnail::path,standard::thumbnail-path",
                        FileQueryInfoFlags.NONE,
                        GLib.PRIORITY_LOW,
                        cancellable,
                        callback
                    )
                },
                finish = { result ->
                    gfile.queryInfoFinish(result)
                }
            )
            
            updatedInfo?.getAttributeString("thumbnail::path") 
                ?: updatedInfo?.getAttributeString("standard::thumbnail-path")
        } catch (e: Exception) {
            null
        }
    }
}
