@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.testing

import com.imbric.core.ifs.*
import com.imbric.core.models.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.*
import kotlinx.datetime.Clock
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

open class InMemoryBackend(
    override val scheme: String = "memory",
    private val latencyProfiler: LatencyProfiler = NoopLatencyProfiler()
) : IOBackend {
    override val displayName: String = "In-Memory Test Backend"
    
    override fun getCapabilities(uri: String) = BackendCapabilities(
        locality = Locality.LOCAL,
        supportsTrash = true,
        supportsSymlinks = true,
        reliableMtime = true,
        reliableSize = true,
        caseSensitive = true
    )

    override suspend fun canPerform(action: FileAction, uri: String): Boolean = true

    // URI -> FileInfo map
    val fs = mutableMapOf<String, FileInfo>()
    val trashFs = mutableMapOf<String, FileInfo>() // For simulating trash
    val failingUris = mutableSetOf<String>()
    
    // Thumbnail support for testing
    private val thumbnailPaths = mutableMapOf<String, String>()
    private val thumbnailFailures = mutableSetOf<String>()
    private val thumbnailUnsupported = mutableSetOf<String>()

    override fun list(uri: String, sortKey: SortKey): Flow<List<FileEntry>> {
        if (failingUris.contains(uri.removeSuffix("/"))) return flowOf(emptyList())
        val normalizedUri = uri.removeSuffix("/")
        val children = fs.values.filter {
            it.uri.substringBeforeLast("/") == normalizedUri && it.uri != normalizedUri
        }
        return flowOf(children)
    }

    override suspend fun getMetadata(uri: String): Result<FileInfo> {
        val normalized = uri.removeSuffix("/")
        if (failingUris.contains(normalized)) return Result.failure(Exception("Injected failure"))
        val info = fs[normalized]
        return if (info != null) Result.success(info) else Result.failure(Exception("Not found: $uri"))
    }

    override fun exists(uri: String): Boolean = fs.containsKey(uri.removeSuffix("/"))

    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> {
        return if (fs.containsKey(uri.removeSuffix("/"))) {
            Result.success(ByteArray(size.toInt()) { 0 })
        } else {
            Result.failure(Exception("Not found"))
        }
    }

    override suspend fun copy(job: FileJob): Flow<TransferProgress> = flow {
        val srcUri = job.source.removeSuffix("/")
        val destUri = job.dest.removeSuffix("/")
        copyRecursive(srcUri, destUri, job.id, job.overwrite)
    }

    private suspend fun FlowCollector<TransferProgress>.copyRecursive(
        srcUri: String,
        destUri: String,
        jobId: Uuid,
        overwrite: Boolean
    ) {
        val info = fs[srcUri] ?: throw Exception("Source not found: $srcUri")
        if (fs.containsKey(destUri) && !overwrite) {
            throw VfsError.AlreadyExists(destUri)
        }
        
        emit(TransferProgress(jobId, srcUri, null, null, 0, 1, 0, 1))
        
        val newName = destUri.substringAfterLast("/")
        fs[destUri] = info.copy(
            uri = destUri, path = destUri, name = newName, displayName = newName
        )
        
        if (info.isDirectory) {
            val children = fs.values.filter { 
                it.uri.substringBeforeLast("/") == srcUri && it.uri != srcUri 
            }.toList()
            for (child in children) {
                val childDestUri = "$destUri/${child.name}"
                copyRecursive(child.uri, childDestUri, jobId, overwrite)
            }
        }
        emit(TransferProgress(jobId, srcUri, destUri, null, 1, 1, 0, 0))
    }

    override suspend fun move(job: FileJob): Flow<TransferProgress> = flow {
        val srcUri = job.source.removeSuffix("/")
        val destUri = job.dest.removeSuffix("/")
        moveRecursive(srcUri, destUri, job.id, job.overwrite)
    }

    private suspend fun FlowCollector<TransferProgress>.moveRecursive(
        srcUri: String,
        destUri: String,
        jobId: Uuid,
        overwrite: Boolean
    ) {
        val info = fs.remove(srcUri) ?: throw Exception("Source not found: $srcUri")
        if (fs.containsKey(destUri) && !overwrite) {
            throw VfsError.AlreadyExists(destUri)
        }
        
        emit(TransferProgress(jobId, srcUri, null, null, 0, 1, 0, 1))
        
        val newName = destUri.substringAfterLast("/")
        fs[destUri] = info.copy(
            uri = destUri, path = destUri, name = newName, displayName = newName
        )
        
        if (info.isDirectory) {
            val children = fs.values.filter { 
                it.uri.substringBeforeLast("/") == srcUri && it.uri != srcUri 
            }.toList()
            for (child in children) {
                val childDestUri = "$destUri/${child.name}"
                moveRecursive(child.uri, childDestUri, jobId, overwrite)
            }
        }
        emit(TransferProgress(jobId, srcUri, destUri, null, 1, 1, 0, 0))
    }

    override suspend fun trash(job: FileJob, recoverTrashUri: Boolean): Result<String> {
        val file = fs[job.source] ?: return Result.failure(VfsError.NotFound(job.source))
        val trashUri = "trash://${file.name}"
        trashFs[job.source] = file
        delete(job)
        return Result.success(if (recoverTrashUri) trashUri else "")
    }

    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> {
        val destUri = originalPath.removeSuffix("/")
        val key = trashFs.keys.find { it == destUri } ?: return Result.failure(Exception("Item not found in trash"))
        val info = trashFs.remove(key)
        return if (info != null) {
            fs[destUri] = info.copy(uri = destUri, path = destUri)
            Result.success(destUri)
        } else {
            Result.failure(Exception("Item not found in trash"))
        }
    }

    override suspend fun delete(job: FileJob): Result<Unit> {
        val srcUri = job.source.removeSuffix("/")
        return if (fs.remove(srcUri) != null) Result.success(Unit) else Result.failure(Exception("Source not found"))
    }

    override suspend fun listTrash(): Result<List<TrashItem>> {
        val items = trashFs.map { (originalPath, info) ->
            TrashItem(
                name = info.name,
                originalPath = originalPath,
                trashPath = "memory-trash://${info.name}",
                deletionDate = kotlin.time.Clock.System.now().toEpochMilliseconds(),
                size = info.size
            )
        }
        return Result.success(items)
    }

    override suspend fun emptyTrash(): Result<Int> {
        val count = trashFs.size
        trashFs.clear()
        return Result.success(count)
    }

    override suspend fun isTrashEmpty(uri: String): Boolean = trashFs.isEmpty()

    override suspend fun createFolder(parentUri: String, name: String): Result<String> {
        val uri = "${parentUri.removeSuffix("/")}/$name"
        fs[uri] = FileInfo(
            path = uri, uri = uri, name = name, displayName = name,
            isDirectory = true, isSymlink = false, symlinkTarget = null,
            size = 0, mimeType = "inode/directory",
            modifiedTime = kotlin.time.Clock.System.now(), isHidden = name.startsWith("."), isWritable = true, iconName = "folder"
        )
        return Result.success(uri)
    }

    override suspend fun createFile(parentUri: String, name: String): Result<String> {
        val uri = "${parentUri.removeSuffix("/")}/$name"
        fs[uri] = FileInfo(
            path = uri, uri = uri, name = name, displayName = name,
            isDirectory = false, isSymlink = false, symlinkTarget = null,
            size = 0, mimeType = "text/plain",
            modifiedTime = kotlin.time.Clock.System.now(), isHidden = name.startsWith("."), isWritable = true, iconName = "text-x-generic"
        )
        return Result.success(uri)
    }

    override suspend fun rename(uri: String, newName: String): Result<String> {
        val srcUri = uri.removeSuffix("/")
        val info = fs.remove(srcUri) ?: return Result.failure(Exception("Not found"))
        val parent = srcUri.substringBeforeLast("/")
        val newUri = "$parent/$newName"
        fs[newUri] = info.copy(uri = newUri, path = newUri, name = newName, displayName = newName)
        return Result.success(newUri)
    }

    override suspend fun executeInverse(payload: UndoAction): Result<Unit> {
        return when (payload) {
            is UndoAction.TransferUndo -> {
                // Transfer undo: delete destinations (for copy/link) or move back (for move)
                if (payload.sources != null) {
                    // Move-back: move destinations back to original source URIs
                    for (i in payload.destinations.indices) {
                        val destUri = payload.destinations[i].removeSuffix("/")
                        val originalUri = payload.sources[i].removeSuffix("/")
                        
                        val info = fs.remove(destUri) ?: return Result.failure(Exception("Source not found: $destUri"))
                        fs[originalUri] = info.copy(
                            uri = originalUri, 
                            path = originalUri, 
                            name = originalUri.substringAfterLast("/"), 
                            displayName = originalUri.substringAfterLast("/")
                        )
                    }
                    Result.success(Unit)
                } else {
                    // Delete: trash destinations (for copy/link undo)
                    for (dest in payload.destinations) {
                        fs.remove(dest.removeSuffix("/"))
                    }
                    Result.success(Unit)
                }
            }
            is UndoAction.TrashUndo -> {
                // Trash undo: restore from trash to original location
                for (i in payload.trashedUris.indices) {
                    val trashedUri = payload.trashedUris[i].removeSuffix("/")
                    val originalUri = payload.originalUris[i].removeSuffix("/")
                    val info = trashFs.remove(trashedUri) ?: return Result.failure(Exception("Trashed file not found"))
                    fs[originalUri] = info.copy(uri = originalUri, path = originalUri, name = originalUri.substringAfterLast("/"), displayName = originalUri.substringAfterLast("/"))
                }
                Result.success(Unit)
            }
            is UndoAction.CreateUndo -> {
                // Create undo: delete the created file/folder
                fs.remove(payload.createdUri.removeSuffix("/"))
                Result.success(Unit)
            }
            is UndoAction.RenameUndo -> {
                // Rename undo: rename back to original name
                rename(payload.currentUri, payload.originalName).map { Unit }
            }
        }
    }

    override fun watch(uri: String): Flow<FileEvent> = callbackFlow { awaitClose { } }
    override fun canHandle(uri: String): Boolean = uri.startsWith("$scheme://") || !uri.contains("://")
    
    // --- Test helpers ---
    
    /**
     * Test helper: move a file to trash (for testing undo).
     */
    fun trashFile(uri: String) {
        val normalized = uri.removeSuffix("/")
        val info = fs.remove(normalized) ?: return
        trashFs[normalized] = info
    }
    
    // --- Thumbnail support for testing ---
    
    /**
     * Test helper: register a thumbnail path for a URI.
     */
    fun registerThumbnail(uri: String, path: String) {
        thumbnailPaths[uri] = path
    }
    
    /**
     * Test helper: mark a URI as having a failed thumbnail.
     */
    fun markThumbnailFailed(uri: String) {
        thumbnailFailures.add(uri)
    }
    
    /**
     * Test helper: mark a URI as not supporting thumbnails.
     */
    fun markThumbnailUnsupported(uri: String) {
        thumbnailUnsupported.add(uri)
    }
    
    override suspend fun getThumbnailPath(uri: String): String? {
        return thumbnailPaths[uri]
    }
    
    override suspend fun generateThumbnail(uri: String): Result<String?> {
        if (thumbnailUnsupported.contains(uri)) {
            return Result.success(null)
        }
        if (thumbnailFailures.contains(uri)) {
            return Result.failure(Exception("Thumbnail generation failed"))
        }
        val path = "/tmp/thumbnails/${uri.hashCode()}.png"
        thumbnailPaths[uri] = path
        return Result.success(path)
    }
}
