@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.ifs.*
import com.imbric.core.models.*
import com.imbric.core.logic.XferArbiter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.callbackFlow
import kotlin.uuid.Uuid
import org.gnome.gio.File
import org.gnome.gio.FileQueryInfoFlags
import org.gnome.gio.FileType
import org.gnome.gio.FileCopyFlags
import org.gnome.gio.FileMonitorFlags
import org.gnome.gio.FileMonitorEvent
import org.gnome.gio.FileCreateFlags
import org.gnome.gio.FileProgressCallback
import org.gnome.glib.GLib
import kotlin.uuid.ExperimentalUuidApi
import org.gnome.gdkpixbuf.GdkPixbuf
import org.gnome.gdkpixbuf.PixbufLoader
import org.gnome.glib.KeyFile
import org.gnome.glib.KeyFileFlags
import kotlin.system.measureTimeMillis

class GioBackend(private val latencyProfiler: LatencyProfiler = PassiveLatencyProfiler()) : IOBackend {
    init {
        org.gnome.gio.Gio.`javagi$ensureInitialized`()
        GdkPixbuf.`javagi$ensureInitialized`()
    }

    override val scheme: String = "file"
    override val displayName: String = "GIO Unified Backend"

    override fun getCapabilities(uri: String): BackendCapabilities {
        val scheme = uri.substringBefore("://", "file")
        val latency = latencyProfiler.getLatency(scheme)

        return when {
            uri.startsWith("trash://") -> BackendCapabilities(
                locality = Locality.VIRTUAL,
                latencyProfile = latency,
                supportsTrash = false, // already in trash
                supportsSymlinks = false
            )
            uri.contains("://") && !uri.startsWith("file://") -> BackendCapabilities(
                locality = Locality.NETWORK,
                latencyProfile = latency,
                supportsTrash = false // many remote mounts don't support trash
            )
            else -> BackendCapabilities(
                locality = Locality.LOCAL,
                latencyProfile = latency,
                supportsTrash = true,
                supportsSymlinks = true
            )
        }
    }

    override suspend fun canPerform(action: FileAction, uri: String): Boolean = withContext(Dispatchers.IO) {
        val gfile = File.newForUri(uri)
        val info = gfile.queryInfo("access::*,standard::*", FileQueryInfoFlags.NONE, null) ?: return@withContext false
        
        when (action) {
            FileAction.READ -> info.getAttributeBoolean("access::can-read")
            FileAction.WRITE -> info.getAttributeBoolean("access::can-write")
            FileAction.DELETE -> info.getAttributeBoolean("access::can-delete")
            FileAction.TRASH -> info.getAttributeBoolean("access::can-trash")
            FileAction.RENAME -> info.getAttributeBoolean("access::can-rename")
            FileAction.EXECUTE -> info.getAttributeBoolean("access::can-execute")
            FileAction.LIST_CHILDREN -> info.fileType == FileType.DIRECTORY
            FileAction.COPY_SOURCE -> info.getAttributeBoolean("access::can-read")
            FileAction.MOVE_SOURCE -> info.getAttributeBoolean("access::can-delete") && info.getAttributeBoolean("access::can-read")
            FileAction.WATCH -> !uri.startsWith("recent://")
        }
    }

    override fun canHandle(uri: String): Boolean {
        val scheme = uri.substringBefore("://", "")
        if (scheme.isEmpty() || scheme == "file" || scheme == "trash") return true
        
        // Dynamically ask GIO what it supports (e.g. smb, sftp, mtp)
        val vfs = org.gnome.gio.Vfs.getDefault()
        return vfs.supportedUriSchemes?.contains(scheme) == true
    }

    private val queryAttributes = "standard::*,time::*,unix::*,owner::*,access::*,trash::*,recent::modified,metadata::activation-uri"

    private fun resolveUniqueTarget(uri: String): String {
        var current = uri
        while (exists(current)) {
            val parent = current.uriParent
            val name = current.uriName
            val newName = XferArbiter.generateNewName(name)
            current = parent.uriJoin(newName)
        }
        return current
    }

    override fun list(uri: String): Flow<FileInfo> = flow {
        val gfile = File.newForUri(uri)
        val scheme = uri.substringBefore("://", "file")

        // Time only the GIO round-trip (enumerateChildren), not the emit loop
        var enumerator: org.gnome.gio.FileEnumerator? = null
        val timeTaken = measureTimeMillis {
            enumerator = gfile.enumerateChildren(queryAttributes, FileQueryInfoFlags.NONE, null)
        }
        latencyProfiler.recordSample(scheme, timeTaken)

        // Emit loop is outside the timer — consumer speed doesn't pollute the profile
        try {
            var info = enumerator?.nextFile(null)
            while (info != null) {
                emit(GioTypeMappers.toImbricFileInfo(gfile, info))
                info = enumerator?.nextFile(null)
            }
        } finally {
            enumerator?.close(null)
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun getMetadata(uri: String): Result<FileInfo> = withContext(Dispatchers.IO) {
        runCatching {
            val gfile = File.newForUri(uri)
            val info = gfile.queryInfo(queryAttributes, FileQueryInfoFlags.NONE, null)
            GioTypeMappers.toImbricFileInfo(gfile, info)
        }
    }

    override suspend fun copy(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.channelFlow {
        val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
        val src = File.newForUri(job.source)
        val dest = File.newForUri(finalDest)
        
        val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
        
        try {
            val progressCb = FileProgressCallback { current, total, _ ->
                trySend(TransferProgress(job.id, job.source, finalDest, null, 0, 1, current, total))
            }

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    src.copyAsync(dest, flags, GLib.PRIORITY_DEFAULT, cancellable, progressCb, callback)
                },
                finish = { result ->
                    src.copyFinish(result)
                }
            )

            // Report success with dynamic InversePayload
            val inverse = InversePayload(
                action = "undo_copy",
                target = finalDest,
                backendId = scheme
            )
            trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
        } catch (e: org.javagi.base.GErrorException) {
            // G_IO_ERROR_WOULD_RECURSE is 25 in GNOME 46
            if (e.code == 25) { 
                copyRecursive(src, dest, job, this@channelFlow)
                // Report success for the recursive operation
                val inverse = InversePayload(
                    action = "undo_copy",
                    target = finalDest,
                    backendId = scheme
                )
                trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
            } else {
                throw translateError(e)
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun move(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.channelFlow {
        val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
        val src = File.newForUri(job.source)
        val dest = File.newForUri(finalDest)
        
        val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
        
        try {
            val progressCb = FileProgressCallback { current, total, _ ->
                trySend(TransferProgress(job.id, job.source, finalDest, null, 0, 1, current, total))
            }

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    src.moveAsync(dest, flags, GLib.PRIORITY_DEFAULT, cancellable, progressCb, callback)
                },
                finish = { result ->
                    src.moveFinish(result)
                }
            )

            // Report success with dynamic InversePayload
            val inverse = InversePayload(
                action = "undo_move",
                target = finalDest,
                dest = job.source,
                backendId = scheme
            )
            trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
        } catch (e: org.javagi.base.GErrorException) {
            // G_IO_ERROR_WOULD_RECURSE is 25 in GNOME 46
            if (e.code == 25) { 
                copyRecursive(src, dest, job, this@channelFlow)
                src.deleteRecursive()
                // Report success for the recursive operation
                val inverse = InversePayload(
                    action = "undo_move",
                    target = finalDest,
                    dest = job.source,
                    backendId = scheme
                )
                trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
            } else {
                throw translateError(e)
            }
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun copyRecursive(
        src: File, 
        dest: File, 
        job: FileJob, 
        channel: kotlinx.coroutines.channels.SendChannel<TransferProgress>
    ) {
        val info = src.queryInfo("standard::type", FileQueryInfoFlags.NONE, null)
        if (info.fileType == FileType.DIRECTORY) {
            if (!dest.queryExists(null)) {
                GioCoroutineBridge.awaitGioAsync(
                    block = { cancellable, callback ->
                        dest.makeDirectoryAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                    },
                    finish = { result ->
                        dest.makeDirectoryFinish(result)
                    }
                )
            }
            
            val enumerator = src.enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            try {
                var childInfo = enumerator.nextFile(null)
                while (childInfo != null) {
                    val name = childInfo.name?.toString()
                    if (!name.isNullOrEmpty()) {
                        val childSrc = src.getChild(name)
                        val childDest = dest.getChild(name)
                        copyRecursive(childSrc, childDest, job, channel)
                    }
                    childInfo = enumerator.nextFile(null)
                    kotlinx.coroutines.yield()
                }
            } finally {
                enumerator.close(null)
            }
        } else {
            val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
            val progressCb = FileProgressCallback { current, total, _ ->
                channel.trySend(TransferProgress(job.id, src.uri, dest.uri, null, 0, 1, current, total))
            }
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    src.copyAsync(dest, flags, GLib.PRIORITY_DEFAULT, cancellable, progressCb, callback)
                },
                finish = { result ->
                    src.copyFinish(result)
                }
            )
        }
    }

    private suspend fun File.deleteRecursive() {
        val info = queryInfo("standard::type", FileQueryInfoFlags.NONE, null)
        if (info.fileType == FileType.DIRECTORY) {
            val enumerator = enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            try {
                var childInfo = enumerator.nextFile(null)
                while (childInfo != null) {
                    val name = childInfo.name?.toString()
                    if (!name.isNullOrEmpty()) {
                        getChild(name).deleteRecursive()
                    }
                    childInfo = enumerator.nextFile(null)
                    kotlinx.coroutines.yield()
                }
            } finally {
                enumerator.close(null)
            }
        }
        
        GioCoroutineBridge.awaitGioAsync(
            block = { cancellable, callback ->
                deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
            },
            finish = { result ->
                deleteFinish(result)
            }
        )
    }

    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val src = File.newForUri(trashPath)
            val dest = File.newForUri(originalPath)
            
            // 1. Ensure the destination parent directory exists
            val parent = dest.parent
            if (parent != null && !parent.queryExists(null)) {
                parent.makeDirectoryWithParents(null)
            }
            
            // 2. Resolve collisions if someone created a new file at the old path
            val finalDestUri = if (dest.queryExists(null)) {
                resolveUniqueTarget(originalPath)
            } else {
                originalPath
            }
            
            val finalDest = File.newForUri(finalDestUri)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    src.moveAsync(finalDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                },
                finish = { result ->
                    src.moveFinish(result)
                }
            )
            Result.success(finalDestUri)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun listTrash(): Result<List<TrashItem>> = withContext(Dispatchers.IO) {
        runCatching {
            val items = mutableListOf<TrashItem>()
            val trashRoot = File.newForUri("trash:///")
            val enumerator = trashRoot.enumerateChildren(
                "standard::name,standard::size,trash::orig-path,trash::deletion-date",
                FileQueryInfoFlags.NONE,
                null
            )
            try {
                var info = enumerator.nextFile(null)
                while (info != null) {
                    val name = info.name?.toString() ?: ""
                    val size = info.size
                    
                    val origPathAttr = info.getAttributeByteString("trash::orig-path")
                    val origPath = origPathAttr ?: ""
                    
                    val dateStr = info.getAttributeString("trash::deletion-date") ?: ""
                    val deletionDate = try { kotlinx.datetime.Instant.parse(dateStr).toEpochMilliseconds() } catch (e: Exception) { 0L }

                    items.add(TrashItem(
                        name = name,
                        originalPath = origPath,
                        trashPath = "trash:///$name",
                        deletionDate = deletionDate,
                        size = size
                    ))
                    info = enumerator.nextFile(null)
                }
            } finally {
                enumerator.close(null)
            }
            items.sortedByDescending { it.deletionDate }
        }
    }

    override suspend fun emptyTrash(): Result<Int> = withContext(Dispatchers.IO) {
        try {
            var deleted = 0
            val trashRoot = File.newForUri("trash:///")
            val enumerator = trashRoot.enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            val children = mutableListOf<File>()
            
            try {
                var info = enumerator.nextFile(null)
                while (info != null) {
                    val name = info.name?.toString()
                    if (!name.isNullOrEmpty()) {
                        children.add(trashRoot.getChild(name))
                    }
                    info = enumerator.nextFile(null)
                }
            } finally {
                enumerator.close(null)
            }

            for (child in children) {
                try {
                    // Use the async delete for each item
                    GioCoroutineBridge.awaitGioAsync(
                        block = { cancellable, callback ->
                            child.deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result ->
                            child.deleteFinish(result)
                        }
                    )
                    deleted++
                } catch (e: Exception) {
                    // Log individual failures but continue emptying the rest
                    org.gnome.glib.GLib.log("Imbric", org.gnome.glib.LogLevelFlags.LEVEL_WARNING, "Failed to delete trash item ${child.uri?.toString() ?: "unknown"}: ${e.message}")
                }
            }
            Result.success(deleted)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun isTrashEmpty(uri: String): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val gfile = File.newForUri(uri)
            val info = gfile.queryInfo("trash::item-count", FileQueryInfoFlags.NONE, null)
            info.getAttributeUint32("trash::item-count") == 0
        }.getOrDefault(true)
    }

    override suspend fun createFolder(parentUri: String, name: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val parent = File.newForUri(parentUri)
            val child = parent.getChild(name)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    child.makeDirectoryAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    child.makeDirectoryFinish(result)
                }
            )
            Result.success(child.uri)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun createFile(parentUri: String, name: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val parent = File.newForUri(parentUri)
            val child = parent.getChild(name)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    child.createAsync(FileCreateFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    child.createFinish(result).close()
                }
            )
            Result.success(child.uri)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun rename(uri: String, newName: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(uri)
            
            val newFile = GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.setDisplayNameAsync(newName, GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    gfile.setDisplayNameFinish(result)
                }
            )
            
            Result.success(newFile?.uri ?: uri)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun mountEnclosingVolume(uri: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(uri)
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    // We use null for MountOperation as we don't have a UI prompter in core
                    gfile.mountEnclosingVolume(org.gnome.gio.MountMountFlags.NONE, null, cancellable, callback)
                },
                finish = { result ->
                    gfile.mountEnclosingVolumeFinish(result)
                }
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun unmount(uri: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(uri)
            val mount = gfile.findEnclosingMount(null) 
                ?: return@withContext Result.failure(Exception("No enclosing mount found for $uri"))
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    mount.unmountWithOperation(org.gnome.gio.MountUnmountFlags.NONE, null, cancellable, callback)
                },
                finish = { result ->
                    mount.unmountWithOperationFinish(result)
                }
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun trash(job: FileJob): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(job.source)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.trashAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    gfile.trashFinish(result)
                }
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun delete(job: FileJob): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(job.source)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    gfile.deleteFinish(result)
                }
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override suspend fun executeInverse(payload: InversePayload): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val target = File.newForUri(payload.target)
            when (payload.action) {
                "undo_copy" -> {
                    GioCoroutineBridge.awaitGioAsync(
                        block = { cancellable, callback ->
                            target.trashAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result ->
                            target.trashFinish(result)
                        }
                    )
                }
                "undo_move" -> {
                    val destUri = payload.dest ?: throw Exception("Original destination missing in payload")
                    val dest = File.newForUri(destUri)
                    GioCoroutineBridge.awaitGioAsync(
                        block = { cancellable, callback ->
                            target.moveAsync(dest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                        },
                        finish = { result ->
                            target.moveFinish(result)
                        }
                    )
                }
                "undo_rename" -> {
                    val originalName = payload.dest?.uriName ?: throw Exception("Original name missing in payload")
                    GioCoroutineBridge.awaitGioAsync(
                        block = { cancellable, callback ->
                            target.setDisplayNameAsync(originalName, GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result ->
                            target.setDisplayNameFinish(result)
                        }
                    )
                }
                "undo_trash" -> {
                    val originalPath = payload.dest ?: throw Exception("Original path missing in payload")
                    restoreFromTrash(payload.target, originalPath).getOrThrow()
                }
                "undo_create" -> {
                    GioCoroutineBridge.awaitGioAsync(
                        block = { cancellable, callback ->
                            target.trashAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result ->
                            target.trashFinish(result)
                        }
                    )
                }
                else -> throw UnsupportedOperationException("Unknown inverse action: ${payload.action}")
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(translateError(e))
        }
    }

    override fun watch(uri: String): Flow<FileEvent> = callbackFlow {
        val gfile = File.newForUri(uri)
        val monitor = gfile.monitor(FileMonitorFlags.NONE, null)
        
        val conn = monitor.onChanged { file, other, eventType ->
            val event = when (eventType) {
                FileMonitorEvent.CREATED -> FileEvent.Created(file?.uri ?: "")
                FileMonitorEvent.DELETED -> FileEvent.Deleted(file?.uri ?: "")
                FileMonitorEvent.CHANGED, FileMonitorEvent.ATTRIBUTE_CHANGED -> FileEvent.Modified(file?.uri ?: "")
                FileMonitorEvent.MOVED_IN -> FileEvent.Created(file?.uri ?: "")
                FileMonitorEvent.MOVED_OUT -> FileEvent.Deleted(file?.uri ?: "")
                FileMonitorEvent.RENAMED -> FileEvent.Renamed(file?.uri ?: "", other?.uri ?: "")
                else -> null
            }
            if (event != null) {
                trySend(event)
            }
        }
        
        awaitClose {
            conn.disconnect()
            monitor.cancel()
        }
    }.flowOn(Dispatchers.IO)

    override fun exists(uri: String): Boolean = File.newForUri(uri).queryExists(null)

    override fun search(query: com.imbric.core.models.VfsQuery): Flow<FileInfo> = flow {
        val rootFile = File.newForUri(query.rootUri)
        val queryLower = query.text.lowercase()
        
        val stack = ArrayDeque<Pair<File, Int>>()
        stack.add(rootFile to 0)
        
        while (stack.isNotEmpty()) {
            val (dir, depth) = stack.removeLast()
            if (depth > query.maxDepth) continue

            val enumerator = try {
                dir.enumerateChildren(queryAttributes, FileQueryInfoFlags.NONE, null)
            } catch (e: Exception) {
                continue
            }
            
            try {
                var info = enumerator.nextFile(null)
                while (info != null) {
                    val name = info.name?.toString()
                    if (name.isNullOrEmpty()) { info = enumerator.nextFile(null); continue }
                    val child = dir.getChild(name)

                    // Skip hidden files if not requested
                    if (!query.includeHidden && (name.startsWith(".") || info.isHidden)) {
                        info = enumerator.nextFile(null)
                        kotlinx.coroutines.yield()
                        continue
                    }
                    
                    // Recurse into subdirectories
                    if (info.fileType == FileType.DIRECTORY && query.recursive) {
                        stack.add(child to depth + 1)
                    }
                    
                    // Match filename against query (case-insensitive)
                    if (name.lowercase().contains(queryLower)) {
                        val fileInfo = GioTypeMappers.toImbricFileInfo(dir, info)
                        if (query.mimeFilter == null || fileInfo.mimeType.startsWith(query.mimeFilter)) {
                            emit(fileInfo)
                        }
                    }
                    
                    info = enumerator.nextFile(null)
                    kotlinx.coroutines.yield() // allow cancellation
                }
            } finally {
                enumerator.close(null)
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = withContext(Dispatchers.IO) {
        runCatching {
            val gfile = File.newForUri(uri)
            val stream = gfile.read(null)
            try {
                val buffer = ByteArray(size.toInt())
                val outBuffer = org.javagi.base.Out(buffer)
                val bytesRead = stream.read(outBuffer, null)
                val finalBuffer = outBuffer.get() ?: buffer
                if (bytesRead < size) {
                    finalBuffer.copyOf(bytesRead.toInt())
                } else {
                    finalBuffer
                }
            } finally {
                stream.close(null)
            }
        }
    }

    override suspend fun enrichMetadata(info: FileInfo): FileInfo = withContext(Dispatchers.IO) {
        var currentInfo = info
        val attrs = currentInfo.attributes.toMutableMap()
        
        // 1. Image Dimensions (64KB Trick)
        val mime = currentInfo.mimeType.lowercase()
        val isImage = mime.startsWith("image/") || mime.endsWith("/webp") || mime.endsWith("/heic") || mime.endsWith("/avif")
        
        if (!currentInfo.isDirectory && isImage) {
            val bytesResult = readHeader(currentInfo.uri, 65536)
            bytesResult.onSuccess { bytes ->
                var width = 0
                var height = 0
                try {
                    val loader = PixbufLoader()
                    loader.onSizePrepared { w, h ->
                        width = w
                        height = h
                    }
                    loader.write(bytes)
                    try { loader.close() } catch (e: Exception) { }
                    
                    if (width > 0 && height > 0) {
                        attrs["std::dimensions"] = "${width}x${height}"
                        attrs["std::aspect-ratio"] = width.toDouble() / height
                    }
                } catch (e: Exception) {
                    // Ignore parsing errors for partial/corrupt images
                }
            }
        }
        
        // 2. .desktop file parsing
        if (currentInfo.name.endsWith(".desktop")) {
            val bytesResult = readHeader(currentInfo.uri, 1024 * 1024) // up to 1MB
            bytesResult.onSuccess { bytes ->
                try {
                    val keyFile = KeyFile()
                    // Convert bytes to string (assuming UTF-8 for desktop files)
                    val content = String(bytes)
                    if (keyFile.loadFromData(content, content.length.toLong(), KeyFileFlags.NONE)) {
                        val group = "Desktop Entry"
                        if (keyFile.hasGroup(group)) {
                            try {
                                val type = keyFile.getString(group, "Type")
                                attrs["desktop::type"] = type
                                
                                val name = keyFile.getString(group, "Name")
                                if (name != null) {
                                    currentInfo = currentInfo.copy(displayName = name)
                                }
                                
                                val icon = keyFile.getString(group, "Icon")
                                if (icon != null) {
                                    currentInfo = currentInfo.copy(iconName = icon)
                                }
                                
                                if (keyFile.hasKey(group, "Exec")) {
                                    attrs["desktop::exec"] = keyFile.getString(group, "Exec")
                                }
                                if (keyFile.hasKey(group, "URL")) {
                                    attrs["desktop::url"] = keyFile.getString(group, "URL")
                                }
                            } catch (e: Exception) {
                                // Missing keys are fine
                            }
                        }
                    }
                } catch (e: Exception) {
                    // Parsing failed
                }
            }
        }
        
        currentInfo.copy(attributes = attrs)
    }

    /**
     * GIO-native thumbnail path lookup.
     * Queries the GIO thumbnail attributes directly instead of going through getMetadata().
     */
    override suspend fun getThumbnailPath(uri: String): String? = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(uri)
            val info = gfile.queryInfo(
                "thumbnail::path,standard::thumbnail-path",
                FileQueryInfoFlags.NONE,
                null
            )
            info?.getAttributeString("thumbnail::path")
                ?: info?.getAttributeString("standard::thumbnail-path")
        } catch (e: Exception) {
            null
        }
    }

    /**
     * GIO-native thumbnail generation.
     * Uses async queryInfo to trigger GIO's built-in thumbnailer.
     */
    override suspend fun generateThumbnail(uri: String): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val gfile = File.newForUri(uri)
            val info = GioCoroutineBridge.awaitGioAsync(
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
            val path = info?.getAttributeString("thumbnail::path")
                ?: info?.getAttributeString("standard::thumbnail-path")
            Result.success(path)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun getUsage(uri: String): Result<DiskUsage?> = withContext(Dispatchers.IO) {
        runCatching {
            val gfile = File.newForUri(uri)
            val info = gfile.queryFilesystemInfo("filesystem::free,filesystem::size", null)
            
            if (info.hasAttribute("filesystem::size") && info.hasAttribute("filesystem::free")) {
                val total = info.getAttributeUint64("filesystem::size")
                val free = info.getAttributeUint64("filesystem::free")
                DiskUsage(totalBytes = total, availableBytes = free)
            } else {
                null
            }
        }
    }

    private fun translateError(e: Exception): Exception {
        return when {
            e is org.gnome.gio.IOException -> when (e.enum) {
                org.gnome.gio.IOErrorEnum.EXISTS -> VfsConflictException(VfsConflictException.EXISTS, e.message ?: "File exists")
                org.gnome.gio.IOErrorEnum.NOT_FOUND -> VfsConflictException(VfsConflictException.NOT_FOUND, e.message ?: "File not found")
                org.gnome.gio.IOErrorEnum.WOULD_RECURSE -> VfsConflictException(VfsConflictException.WOULD_RECURSE, e.message ?: "Directory operation would recurse")
                else -> e
            }
            // GIO error codes: FAILED=0, NOT_FOUND=1, EXISTS=2, WOULD_RECURSE=25
            // Maps to VfsConflictException constants (EXISTS=1, NOT_FOUND=2) by semantic name, not numeric value
            e is org.javagi.base.GErrorException -> when (e.code) {
                1 -> VfsConflictException(VfsConflictException.NOT_FOUND, e.message ?: "File not found")
                2 -> VfsConflictException(VfsConflictException.EXISTS, e.message ?: "File exists")
                25 -> VfsConflictException(VfsConflictException.WOULD_RECURSE, e.message ?: "Directory operation would recurse")
                else -> e
            }
            else -> e
        }
    }
}
