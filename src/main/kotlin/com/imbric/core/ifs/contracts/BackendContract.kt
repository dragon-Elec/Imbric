package com.imbric.core.ifs.contracts

import com.imbric.core.ifs.*
import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * Common exception for VFS conflicts.
 * @deprecated Use [VfsError] sealed class hierarchy instead.
 */
@Deprecated("Use VfsError sealed class hierarchy instead")
open class VfsConflictException(val code: Int, message: String) : Exception(message) {
    companion object {
        const val EXISTS = 1
        const val NOT_FOUND = 2
        const val WOULD_RECURSE = 25
    }
}

interface BackendContract {

    val scheme: String
    val displayName: String

    /**
     * Contextual capabilities for a specific URI.
     */
    fun getCapabilities(uri: String): BackendCapabilities

    /**
     * Checks if a specific action is allowed on the given URI.
     * This encapsulates complex native logic (Permissions, Quotas, Backend state).
     */
    suspend fun canPerform(action: FileAction, uri: String): Boolean

    // Reads
    suspend fun list(uri: String, sortKey: SortKey = SortKey.NAME): List<FileEntry>
    suspend fun getMetadata(uri: String): Result<FileInfo>

    // Bulk metadata default implementation
    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    suspend fun getMetadata(uris: List<String>): List<Result<FileInfo>> = withContext(Dispatchers.IO.limitedParallelism(10)) {
        uris.map { uri -> async { getMetadata(uri) } }.awaitAll()
    }

    fun exists(uri: String): Boolean

    /**
     * Reads a small chunk from the beginning of a file.
     * Used for the "64KB Trick" to extract metadata without downloading the full file.
     */
    suspend fun readHeader(uri: String, size: Long): Result<ByteArray>

    /**
     * Enriches basic metadata with backend-specific heavy data (like image dimensions, desktop app parsing).
     */
    suspend fun enrichMetadata(info: FileInfo): FileInfo = info

    /**
     * Retrieves disk usage information for the filesystem containing the given URI.
     */
    suspend fun getUsage(uri: String): Result<DiskUsage?> = Result.success(null)

    /**
     * Recursively counts all items (files + directories) and total size under the given URI.
     * Default implementation composes [list()] — backends can override with native implementations
     * (e.g., Tracker3 SPARQL index, SMB get_folder_size RPC).
     *
     * @param uri The directory URI to count recursively
     * @param maxDepth Maximum recursion depth (default: unlimited)
     * @return Flow of intermediate [DeepCount] results, final result has [DeepCount.isComplete]=true
     */
    fun deepCount(uri: String, maxDepth: Int = Int.MAX_VALUE): Flow<DeepCount> = flow {
        var dirs = 0; var files = 0; var totalSize = 0L
        val stack = ArrayDeque<Pair<String, Int>>()
        stack.add(uri to 0)
        while (stack.isNotEmpty()) {
            val (dirUri, depth) = stack.removeLast()
            if (depth > maxDepth) {
                kotlinx.coroutines.yield()
                continue
            }

            try {
                val items = list(dirUri)
                for (info in items) {
                    if (info.isDirectory) {
                        dirs++
                        stack.add(info.uri to depth + 1)
                    } else {
                        files++
                        totalSize += info.size
                    }
                    if ((files + dirs) % 100 == 0) {
                        emit(DeepCount(dirs, files, totalSize, isComplete = false))
                        kotlinx.coroutines.yield()
                    }
                }
                kotlinx.coroutines.yield()
            } catch (e: Exception) {
                // Skip directories we can't list (permissions, etc.) instead of crashing
                // We could optionally emit an error state here if DeepCount supported it
            }
        }
        emit(DeepCount(dirs, files, totalSize, isComplete = true))
    }

    fun watch(uri: String): Flow<FileEvent> = emptyFlow()

    fun canHandle(uri: String): Boolean =
        uri.startsWith("$scheme://") || (!uri.contains("://") && scheme == "file")

    /**
     * Helper to get the trash-capable backends for this FS.
     */
    suspend fun getTrashBackend(registry: BackendRegistry): BackendContract? {
        val rootUri = "$scheme:///"
        val backend = registry.get(rootUri)
        return if (backend != null && backend.getCapabilities(rootUri).supportsTrash) backend else null
    }
}
