package com.imbric.core.ifs.backends

import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.BackendCapabilities
import com.imbric.core.ifs.LatencyProfile
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.FileAction
import com.imbric.core.models.FileInfo
import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import com.imbric.core.models.TrashItem
import com.imbric.core.models.DiskUsage
import com.imbric.core.ifs.FileEvent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import org.gnome.gio.File

class GioSearchBackend(private val fallback: GioBackend = GioBackend()) : IOBackend {
    override val scheme: String = "search"
    override val displayName: String = "GNOME Tracker Search"

    override fun getCapabilities(uri: String): BackendCapabilities {
        return BackendCapabilities(
            locality = Locality.VIRTUAL,
            latencyProfile = LatencyProfile.LOW,
            supportsTrash = false,
            supportsSymlinks = false
        )
    }

    override suspend fun canPerform(action: FileAction, uri: String): Boolean {
        return action == FileAction.READ || action == FileAction.LIST_CHILDREN
    }

    override fun canHandle(uri: String): Boolean {
        return uri.startsWith("search://")
    }

    override fun list(uri: String): Flow<FileInfo> {
        // search:///query?root=...&mime=...
        val query = uri.substringAfter("search:///", "").substringBefore("?")
        val params = uri.substringAfter("?", "").split("&").associate {
            val parts = it.split("=")
            if (parts.size == 2) parts[0] to parts[1] else it to ""
        }
        val root = params["root"]?.let { java.net.URLDecoder.decode(it, "UTF-8") } ?: "file:///"
        val mime = params["mime"]
        
        return search(query, root, mime)
    }

    override fun search(query: String, root: String, mimeFilter: String?): Flow<FileInfo> = flow {
        if (query.isBlank()) return@flow

        // 1. Try Tracker3
        val trackerResults = runTrackerSearch(query)
        if (trackerResults != null) {
            trackerResults.forEach { uri ->
                // Only return results that are within the requested root
                if (uri.startsWith(root)) {
                    val info = fallback.getMetadata(uri).getOrNull()
                    if (info != null) {
                        if (mimeFilter == null || info.mimeType.startsWith(mimeFilter)) {
                            emit(info)
                        }
                    }
                }
            }
        } else {
            // 2. Fallback to manual walk
            emitAll(fallback.search(query, root, mimeFilter))
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun runTrackerSearch(query: String): List<String>? = withContext(Dispatchers.IO) {
        try {
            val process = ProcessBuilder("tracker3", "search", "--disable-color", query)
                .start()
            
            val results = mutableListOf<String>()
            BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                var line = reader.readLine()
                while (line != null) {
                    val trimmed = line.trim()
                    if (trimmed.startsWith("file://")) {
                        results.add(trimmed)
                    }
                    line = reader.readLine()
                }
            }
            
            if (process.waitFor() == 0) results else null
        } catch (e: Exception) {
            null
        }
    }

    // Delegate other methods to fallback or fail
    override suspend fun getMetadata(uri: String): Result<FileInfo> = fallback.getMetadata(uri)
    override fun exists(uri: String): Boolean = fallback.exists(uri)
    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = fallback.readHeader(uri, size)
    override suspend fun copy(job: FileJob): Flow<TransferProgress> = fallback.copy(job)
    override suspend fun move(job: FileJob): Flow<TransferProgress> = fallback.move(job)
    override suspend fun trash(job: FileJob): Result<Unit> = fallback.trash(job)
    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = fallback.restoreFromTrash(trashPath, originalPath)
    override suspend fun delete(job: FileJob): Result<Unit> = fallback.delete(job)
    override suspend fun createFolder(parentUri: String, name: String): Result<String> = fallback.createFolder(parentUri, name)
    override suspend fun createFile(parentUri: String, name: String): Result<String> = fallback.createFile(parentUri, name)
    override suspend fun rename(uri: String, newName: String): Result<String> = fallback.rename(uri, newName)
}