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
    override val scheme: String = "memory"
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

    override fun list(uri: String): Flow<FileInfo> {
        if (failingUris.contains(uri.removeSuffix("/"))) return emptyFlow()
        val normalizedUri = uri.removeSuffix("/")
        val children = fs.values.filter { 
            it.uri.substringBeforeLast("/") == normalizedUri && it.uri != normalizedUri
        }
        return children.asFlow()
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
            throw VfsConflictException(VfsConflictException.EXISTS, "Destination already exists: $destUri")
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
            throw VfsConflictException(VfsConflictException.EXISTS, "Destination already exists: $destUri")
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

    override suspend fun trash(job: FileJob): Result<Unit> {
        val srcUri = job.source.removeSuffix("/")
        val info = fs.remove(srcUri)
        return if (info != null) {
            trashFs[srcUri] = info
            Result.success(Unit)
        } else {
            Result.failure(Exception("Source not found: $srcUri"))
        }
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
                deletionDate = Clock.System.now().toEpochMilliseconds(),
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
            modifiedTime = Clock.System.now(), isHidden = name.startsWith("."), isWritable = true, iconName = "folder"
        )
        return Result.success(uri)
    }

    override suspend fun createFile(parentUri: String, name: String): Result<String> {
        val uri = "${parentUri.removeSuffix("/")}/$name"
        fs[uri] = FileInfo(
            path = uri, uri = uri, name = name, displayName = name,
            isDirectory = false, isSymlink = false, symlinkTarget = null,
            size = 0, mimeType = "text/plain",
            modifiedTime = Clock.System.now(), isHidden = name.startsWith("."), isWritable = true, iconName = "text-x-generic"
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

    override suspend fun executeInverse(payload: InversePayload): Result<Unit> {
        return when (payload.action) {
            "undo_copy" -> {
                val target = payload.target.removeSuffix("/")
                fs.remove(target)
                Result.success(Unit)
            }
            "undo_move" -> {
                val target = payload.target.removeSuffix("/")
                val dest = payload.dest?.removeSuffix("/") ?: return Result.failure(Exception("Missing dest"))
                val info = fs.remove(target) ?: return Result.failure(Exception("Source not found"))
                val newName = dest.substringAfterLast("/")
                fs[dest] = info.copy(uri = dest, path = dest, name = newName, displayName = newName)
                Result.success(Unit)
            }
            "undo_trash" -> {
                restoreFromTrash(payload.target, payload.dest ?: payload.target).map { Unit }
            }
            "undo_rename" -> {
                rename(payload.target, (payload.dest ?: "").substringAfterLast("/")).map { Unit }
            }
            else -> Result.failure(UnsupportedOperationException("Action not supported in memory: ${payload.action}"))
        }
    }

    override fun watch(uri: String): Flow<FileEvent> = callbackFlow { awaitClose { } }
    override fun canHandle(uri: String): Boolean = uri.startsWith("$scheme://") || !uri.contains("://")
}
