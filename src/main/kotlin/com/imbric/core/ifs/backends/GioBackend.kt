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
import kotlinx.coroutines.suspendCancellableCoroutine
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
import org.gnome.gio.Cancellable
import org.gnome.gio.FileProgressCallback
import org.gnome.gio.AsyncReadyCallback
import org.gnome.glib.GLib
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.uuid.ExperimentalUuidApi
import org.gnome.gdkpixbuf.GdkPixbuf
import org.gnome.gdkpixbuf.PixbufLoader
import org.gnome.glib.KeyFile
import org.gnome.glib.KeyFileFlags

class GioBackend : IOBackend {
    init {
        org.gnome.gio.Gio.`javagi$ensureInitialized`()
        GdkPixbuf.`javagi$ensureInitialized`()
    }

    override val scheme: String = "file"
    override val displayName: String = "GIO Unified Backend"

    override fun getCapabilities(uri: String): BackendCapabilities {
        return when {
            uri.startsWith("trash://") -> BackendCapabilities(
                locality = Locality.VIRTUAL,
                supportsTrash = false, // already in trash
                supportsSymlinks = false
            )
            uri.contains("://") && !uri.startsWith("file://") -> BackendCapabilities(
                locality = Locality.NETWORK,
                supportsTrash = false // many remote mounts don't support trash
            )
            else -> BackendCapabilities(
                locality = Locality.LOCAL,
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

    private val queryAttributes = "standard::*,time::*,unix::*,owner::*,access::*,trash::*"

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
        val enumerator = gfile.enumerateChildren(queryAttributes, FileQueryInfoFlags.NONE, null)
        
        try {
            var info = enumerator.nextFile(null)
            while (info != null) {
                emit(GioTypeMappers.toImbricFileInfo(gfile, info))
                info = enumerator.nextFile(null)
            }
        } finally {
            enumerator.close(null)
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
        withContext(Dispatchers.IO) {
            val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
            val src = File.newForUri(job.source)
            val dest = File.newForUri(finalDest)
            
            val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
            
            try {
                src.copy(dest, flags, null) { current, total, _ ->
                    trySend(TransferProgress(job.id, job.source, finalDest, 0, 1, current, total))
                }
            } catch (e: org.javagi.base.GErrorException) {
                // G_IO_ERROR_WOULD_RECURSE is 25 in GNOME 46
                if (e.code == 25) { 
                    copyRecursive(src, dest, job, this@channelFlow)
                } else {
                    throw translateError(e)
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun move(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.channelFlow {
        withContext(Dispatchers.IO) {
            val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
            val src = File.newForUri(job.source)
            val dest = File.newForUri(finalDest)
            
            val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
            
            try {
                src.move(dest, flags, null) { current, total, _ ->
                    trySend(TransferProgress(job.id, job.source, finalDest, 0, 1, current, total))
                }
            } catch (e: org.javagi.base.GErrorException) {
                // G_IO_ERROR_WOULD_RECURSE is 25 in GNOME 46
                if (e.code == 25) { 
                    copyRecursive(src, dest, job, this@channelFlow)
                    src.deleteRecursive()
                } else {
                    throw translateError(e)
                }
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
                dest.makeDirectory(null)
            }
            
            val enumerator = src.enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            try {
                var childInfo = enumerator.nextFile(null)
                while (childInfo != null) {
                    val childSrc = src.getChild(childInfo.name!!)
                    val childDest = dest.getChild(childInfo.name!!)
                    copyRecursive(childSrc, childDest, job, channel)
                    childInfo = enumerator.nextFile(null)
                }
            } finally {
                enumerator.close(null)
            }
        } else {
            val flags = if (job.overwrite) FileCopyFlags.OVERWRITE else FileCopyFlags.NONE
            src.copy(dest, flags, null) { current, total, _ ->
                channel.trySend(TransferProgress(job.id, src.uri, dest.uri, 0, 1, current, total))
            }
        }
    }

    private fun File.deleteRecursive() {
        val info = queryInfo("standard::type", FileQueryInfoFlags.NONE, null)
        if (info.fileType == FileType.DIRECTORY) {
            val enumerator = enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            try {
                var childInfo = enumerator.nextFile(null)
                while (childInfo != null) {
                    getChild(childInfo.name!!).deleteRecursive()
                    childInfo = enumerator.nextFile(null)
                }
            } finally {
                enumerator.close(null)
            }
        }
        delete(null)
    }

    override suspend fun trash(job: FileJob): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            File.newForUri(job.source).trash(null)
            Unit
        }
    }

    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
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
            src.move(finalDest, FileCopyFlags.NONE, null, null)
            finalDestUri
        }
    }

    override suspend fun delete(job: FileJob): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            File.newForUri(job.source).delete(null)
            Unit
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
                    val name = info.name ?: ""
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
        runCatching {
            var deleted = 0
            val trashRoot = File.newForUri("trash:///")
            val enumerator = trashRoot.enumerateChildren("standard::name", FileQueryInfoFlags.NONE, null)
            try {
                var info = enumerator.nextFile(null)
                while (info != null) {
                    val child = trashRoot.getChild(info.name!!)
                    try {
                        child.deleteRecursive()
                        deleted++
                    } catch (e: Exception) { }
                    info = enumerator.nextFile(null)
                }
            } finally {
                enumerator.close(null)
            }
            deleted
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
        runCatching {
            val parent = File.newForUri(parentUri)
            val child = parent.getChild(name)
            child.makeDirectory(null)
            child.uri
        }
    }

    override suspend fun createFile(parentUri: String, name: String): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val parent = File.newForUri(parentUri)
            val child = parent.getChild(name)
            child.create(FileCreateFlags.NONE, null).close()
            child.uri
        }
    }

    override suspend fun rename(uri: String, newName: String): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val gfile = File.newForUri(uri)
            val newFile = gfile.setDisplayName(newName, null)
            newFile.uri
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

    override fun search(query: String, root: String, mimeFilter: String?): Flow<FileInfo> = flow {
        val rootFile = File.newForUri(root)
        val queryLower = query.lowercase()
        val queryAttrs = "standard::*,time::*,unix::*,owner::*,access::*"
        
        val stack = ArrayDeque<File>()
        stack.add(rootFile)
        
        while (stack.isNotEmpty()) {
            val dir = stack.removeLast()
            val enumerator = try {
                dir.enumerateChildren(queryAttrs, FileQueryInfoFlags.NONE, null)
            } catch (e: Exception) {
                continue
            }
            
            try {
                var info = enumerator.nextFile(null)
                while (info != null) {
                    val name = info.name ?: ""
                    val child = dir.getChild(name)
                    
                    // Recurse into subdirectories
                    if (info.fileType == FileType.DIRECTORY) {
                        stack.add(child)
                    }
                    
                    // Match filename against query (case-insensitive)
                    if (name.lowercase().contains(queryLower)) {
                        val fileInfo = GioTypeMappers.toImbricFileInfo(dir, info)
                        if (mimeFilter == null || fileInfo.mimeType.startsWith(mimeFilter)) {
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

    internal suspend fun File.copySuspend(
        destination: File,
        flags: FileCopyFlags,
        ioPriority: Int,
        cancellable: Cancellable?,
        progressCallback: FileProgressCallback?
    ): Unit = suspendCancellableCoroutine { cont ->
        val callback = AsyncReadyCallback { source, result, _ ->
            try {
                (source as? File ?: this@copySuspend).copyFinish(result)
                cont.resume(Unit)
            } catch (e: org.javagi.base.GErrorException) {
                cont.resumeWithException(translateError(e))
            } catch (e: Exception) {
                cont.resumeWithException(e)
            }
        }
        
        GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
            this@copySuspend.copyAsync(destination, flags, ioPriority, cancellable, progressCallback, callback)
            false
        }
        
        cont.invokeOnCancellation {
            cancellable?.cancel()
        }
    }

    internal suspend fun File.moveSuspend(
        destination: File,
        flags: FileCopyFlags,
        ioPriority: Int,
        cancellable: Cancellable?,
        progressCallback: FileProgressCallback?
    ): Unit = suspendCancellableCoroutine { cont ->
        val callback = AsyncReadyCallback { source, result, _ ->
            try {
                (source as? File ?: this@moveSuspend).moveFinish(result)
                cont.resume(Unit)
            } catch (e: org.javagi.base.GErrorException) {
                cont.resumeWithException(translateError(e))
            } catch (e: Exception) {
                cont.resumeWithException(e)
            }
        }
        
        GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
            this@moveSuspend.moveAsync(destination, flags, ioPriority, cancellable, progressCallback, callback)
            false
        }
        
        cont.invokeOnCancellation {
            cancellable?.cancel()
        }
    }

    private fun translateError(e: org.javagi.base.GErrorException): Exception {
        return when (e.code) {
            2 -> VfsConflictException(VfsConflictException.EXISTS, e.message ?: "File exists")
            1 -> VfsConflictException(VfsConflictException.NOT_FOUND, e.message ?: "File not found")
            25 -> VfsConflictException(VfsConflictException.WOULD_RECURSE, e.message ?: "Directory operation would recurse")
            else -> e
        }
    }
}
