@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs

import com.imbric.core.models.*
import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import com.imbric.core.models.TrashItem
import com.imbric.core.models.DiskUsage
import com.imbric.core.models.DeepCount
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

import com.imbric.core.models.VfsError

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

interface IOBackend {

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
    fun list(uri: String, sortKey: SortKey = SortKey.NAME): Flow<FileEntry>
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
                list(dirUri).collect { info ->
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

    /**
     * Returns the path to a thumbnail for the given URI, if available.
     * Default implementation reads the `thumbnailPath` from [getMetadata].
     * Backends can override with native thumbnail cache lookups.
     */
    suspend fun getThumbnailPath(uri: String): String? {
        return getMetadata(uri).getOrNull()?.thumbnailPath
    }

    /**
     * Triggers asynchronous thumbnail generation for the given URI.
     * Default is a no-op. Backends with native thumbnailers (GIO, Tracker3) override this.
     *
     * @return The path to the generated thumbnail, or null if generation is not supported
     */
    suspend fun generateThumbnail(uri: String): Result<String?> = Result.success(null)

    // Writes
    suspend fun copy(job: FileJob): Flow<TransferProgress>
    suspend fun move(job: FileJob): Flow<TransferProgress>
    suspend fun trash(job: FileJob, recoverTrashUri: Boolean = true): Result<String>
    suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String>
    suspend fun delete(job: FileJob): Result<Unit>
    suspend fun createFolder(parentUri: String, name: String): Result<String>
    suspend fun createFile(parentUri: String, name: String): Result<String>
    suspend fun rename(uri: String, newName: String): Result<String>

    /**
     * Creates a symbolic link at [linkUri] pointing to [targetUri].
     * Default returns UnsupportedOperationException — backends with native symlink support override this.
     */
    suspend fun createLink(targetUri: String, linkUri: String): Result<String> = Result.failure(UnsupportedOperationException("Symlink creation not supported"))

    // Recent Files Operations
    /**
     * Adds a file to the recent files list.
     * Default returns UnsupportedOperationException — backends with recent file support override this.
     */
    suspend fun addToRecent(uri: String, mimeType: String? = null): Result<Unit> = Result.failure(UnsupportedOperationException("Recent files not supported"))

    /**
     * Removes a file from the recent files list.
     */
    suspend fun removeFromRecent(uri: String): Result<Unit> = Result.failure(UnsupportedOperationException("Recent files not supported"))

    /**
     * Purges all recent files older than [olderThanMs] milliseconds.
     * If [olderThanMs] is 0, purges all recent files.
     * Returns the number of items purged.
     */
    suspend fun purgeRecent(olderThanMs: Long = 0): Result<Int> = Result.failure(UnsupportedOperationException("Recent files not supported"))

    // Archive Operations
    /**
     * Extracts an archive to the given destination directory.
     * Default returns UnsupportedOperationException — backends with archive support override this.
     */
    suspend fun extractArchive(archiveUri: String, destDirUri: String): Result<String> = Result.failure(UnsupportedOperationException("Archive extraction not supported"))

    /**
     * Compresses files/directories into an archive.
     * Default returns UnsupportedOperationException — backends with archive support override this.
     */
    suspend fun compressArchive(sourceUris: List<String>, destArchiveUri: String): Result<String> = Result.failure(UnsupportedOperationException("Archive compression not supported"))

    /**
     * Mounts the volume enclosing the given URI.
     */
    suspend fun mountEnclosingVolume(uri: String): Result<Unit> = Result.failure(UnsupportedOperationException("Mounting not supported"))

    /**
     * Unmounts the volume enclosing the given URI.
     */
    suspend fun unmount(uri: String): Result<Unit> = Result.failure(UnsupportedOperationException("Unmounting not supported"))

    /**
     * Executes an inverse operation generated by the backend.
     * This is the "Cleaner" principle: the backend that created the change handles the undo.
     */
    suspend fun executeInverse(payload: com.imbric.core.models.UndoAction): Result<Unit> = Result.failure(UnsupportedOperationException("Inverse execution not supported"))

    // Trash Operations
    suspend fun listTrash(): Result<List<TrashItem>> = Result.failure(UnsupportedOperationException("Trash not supported"))
    suspend fun emptyTrash(): Result<Int> = Result.failure(UnsupportedOperationException("Trash not supported"))
    suspend fun isTrashEmpty(uri: String): Boolean = true

    // Optional (default no-ops)
    fun search(query: com.imbric.core.models.VfsQuery): Flow<FileEntry> = flow {
        val stack = ArrayDeque<Pair<String, Int>>()
        stack.add(query.rootUri to 0)
        
        while (stack.isNotEmpty()) {
            val (dirUri, depth) = stack.removeLast()
            if (depth > query.maxDepth) continue
            
            try {
                list(dirUri).collect { info ->
                    // 1. Recurse
                    if (info.isDirectory && query.recursive) {
                        stack.add(info.uri to depth + 1)
                    }
                    
                    // 2. Filter
                    if (!query.includeHidden && info.isVisiblyHidden()) return@collect
                    
                    val matchesText = query.text.isEmpty() || info.name.contains(query.text, ignoreCase = true)
                    if (!matchesText) return@collect
                    
                    val matchesMime = query.mimeFilter == null || info.mimeType.startsWith(query.mimeFilter)
                    if (!matchesMime) return@collect
                    
                    val mtime = info.modifiedTime?.toEpochMilliseconds()
                    val matchesDate = (query.modifiedAfter == null || (mtime != null && mtime >= query.modifiedAfter)) &&
                                       (query.modifiedBefore == null || (mtime != null && mtime <= query.modifiedBefore))
                    if (!matchesDate) return@collect
                    
                    val matchesSize = (query.minSize == null || info.size >= query.minSize) &&
                                       (query.maxSize == null || info.size <= query.maxSize)
                    if (!matchesSize) return@collect
                    
                    if (query.starredOnly && (info !is FileInfo || !info.isStarred)) return@collect
                    
                    emit(info)
                }
            } catch (e: Exception) {
                // Skip unreadable dirs
            }
        }
    }
    fun watch(uri: String): Flow<FileEvent> = emptyFlow()

    fun canHandle(uri: String): Boolean =
        uri.startsWith("$scheme://") || (!uri.contains("://") && scheme == "file")

    /**
     * Helper to get the trash-capable backends for this FS.
     */
    suspend fun getTrashBackend(registry: BackendRegistry): IOBackend? {
        val rootUri = "$scheme:///"
        val backend = registry.getIo(rootUri)
        return if (backend != null && backend.getCapabilities(rootUri).supportsTrash) backend else null
    }
}
