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
import kotlin.uuid.ExperimentalUuidApi
import org.gnome.gio.File
import org.gnome.gio.FileQueryInfoFlags
import org.gnome.gio.FileType
import org.gnome.gio.FileCopyFlags
import org.gnome.gio.FileMonitorFlags
import org.gnome.gio.FileMonitorEvent
import org.gnome.gio.FileCreateFlags
import org.gnome.gio.FileProgressCallback
import org.gnome.glib.GLib
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
        if (action == FileAction.WATCH) return@withContext !uri.startsWith("recent://")
        
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
        }
    }

    override fun canHandle(uri: String): Boolean {
        val scheme = uri.substringBefore("://", "")
        if (scheme.isEmpty() || scheme == "file" || scheme == "trash") return true
        
        // Dynamically ask GIO what it supports (e.g. smb, sftp, mtp)
        val vfs = org.gnome.gio.Vfs.getDefault()
        return vfs.supportedUriSchemes?.contains(scheme) == true
    }

    private val queryAttributes = "standard::name,standard::display-name,standard::type,standard::is-hidden,standard::size,standard::content-type,standard::is-symlink,standard::symlink-target,time::modified,time::access,time::created,access::can-read,access::can-write,access::can-execute,unix::mode,owner::user,owner::group,standard::icon,standard::symbolic-icon,standard::thumbnail-path,metadata::emblems"

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
        val timer = PipelineTimer.current()

        timer?.mark("gio_list_start", detail = uri)

        val enumerator = GioCoroutineBridge.awaitGioAsync<org.gnome.gio.FileEnumerator>(
            block = { cancellable, callback ->
                gfile.enumerateChildrenAsync(queryAttributes, FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, callback)
            },
            finish = { result ->
                gfile.enumerateChildrenFinish(result)
            }
        )

        timer?.mark("gio_enumerate_done")

        val parentUri = uri.trimEnd('/')
        val parentPath = gfile.path?.toString()?.trimEnd('/')

        var totalEmitted = 0
        try {
            while (true) {
                val fileInfos = GioCoroutineBridge.awaitGioAsync<org.gnome.glib.List<org.gnome.gio.FileInfo>>(
                    block = { cancellable, callback ->
                        enumerator.nextFilesAsync(200, GLib.PRIORITY_DEFAULT, cancellable, callback)
                    },
                    finish = { result ->
                        enumerator.nextFilesFinish(result)
                    }
                )

                if (fileInfos.isEmpty()) break

                for (info in fileInfos) {
                    if (info == null) continue
                    val name = info.name?.toString() ?: ""
                    val childFile = gfile.getChild(name)
                    emit(GioTypeMappers.toImbricFileInfo(childFile, info))
                    totalEmitted++
                }
                timer?.mark("gio_batch_emitted", itemCount = totalEmitted)
            }
        } finally {
            enumerator.close(null)
        }

        timer?.mark("gio_list_done", itemCount = totalEmitted)
    }.flowOn(Dispatchers.IO)

    override suspend fun getMetadata(uri: String): Result<FileInfo> = withVfsErrorHandling(uri) {
        val gfile = File.newForUri(uri)
        val info = gfile.queryInfo(queryAttributes, FileQueryInfoFlags.NONE, null)
        GioTypeMappers.toImbricFileInfo(gfile, info, extractAllAttributes = true)
    }

    override suspend fun copy(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.channelFlow {
        val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
        val src = File.newForUri(job.source)
        val dest = File.newForUri(finalDest)
        
        val flags = if (job.overwrite) setOf(FileCopyFlags.OVERWRITE, FileCopyFlags.ALL_METADATA) else setOf(FileCopyFlags.ALL_METADATA)
        
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

            // Report success with dynamic UndoAction
            val inverse = UndoAction.TransferUndo(
                undoLabel = "Copy",
                itemDescription = job.source.substringAfterLast("/"),
                destinations = listOf(finalDest),
                backendId = scheme
            )
            trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
        } catch (e: Exception) {
            val translatedErr = translateError(e, job.source)
            if (translatedErr is VfsError.WouldRecurse) { 
                copyRecursive(src, dest, job, this@channelFlow)
                // Report success for the recursive operation
                val inverse = UndoAction.TransferUndo(
                    undoLabel = "Copy",
                    itemDescription = job.source.substringAfterLast("/"),
                    destinations = listOf(finalDest),
                    backendId = scheme
                )
                trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
            } else {
                throw translatedErr
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun move(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.channelFlow {
        val finalDest = if (job.autoRename) resolveUniqueTarget(job.dest) else job.dest
        val src = File.newForUri(job.source)
        val dest = File.newForUri(finalDest)
        
        val flags = if (job.overwrite) setOf(FileCopyFlags.OVERWRITE, FileCopyFlags.ALL_METADATA) else setOf(FileCopyFlags.ALL_METADATA)
        
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

            // Report success with dynamic UndoAction
            val inverse = UndoAction.TransferUndo(
                undoLabel = "Move",
                itemDescription = job.source.substringAfterLast("/"),
                destinations = listOf(finalDest),
                sources = listOf(job.source),
                srcDir = job.source.substringBeforeLast("/"),
                backendId = scheme
            )
            trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
        } catch (e: Exception) {
            val translatedErr = translateError(e, job.source)
            if (translatedErr is VfsError.WouldRecurse) { 
                copyRecursive(src, dest, job, this@channelFlow)
                src.deleteRecursive()
                // Report success for the recursive operation
                val inverse = UndoAction.TransferUndo(
                    undoLabel = "Move",
                    itemDescription = job.source.substringAfterLast("/"),
                    destinations = listOf(finalDest),
                    sources = listOf(job.source),
                    srcDir = job.source.substringBeforeLast("/"),
                    backendId = scheme
                )
                trySend(TransferProgress(job.id, job.source, finalDest, inverse, 1, 1, 0, 0))
            } else {
                throw translatedErr
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
            val flags = if (job.overwrite) setOf(FileCopyFlags.OVERWRITE, FileCopyFlags.ALL_METADATA) else setOf(FileCopyFlags.ALL_METADATA)
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

    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = withVfsErrorHandling(trashPath) {
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
        finalDestUri
    }

    override suspend fun listTrash(): Result<List<TrashItem>> = withVfsErrorHandling("trash:///") {
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

    override suspend fun isTrashEmpty(uri: String): Boolean = withVfsErrorHandling(uri) {
        val gfile = File.newForUri(uri)
        val info = gfile.queryInfo("trash::item-count", FileQueryInfoFlags.NONE, null)
        info.getAttributeUint32("trash::item-count") == 0
    }.getOrDefault(true)

    override suspend fun createFolder(parentUri: String, name: String): Result<String> = withVfsErrorHandling("$parentUri/$name") {
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
        child.uri
    }

    override suspend fun createFile(parentUri: String, name: String): Result<String> = withVfsErrorHandling("$parentUri/$name") {
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
        child.uri
    }

    override suspend fun rename(uri: String, newName: String): Result<String> = withVfsErrorHandling(uri) {
        val gfile = File.newForUri(uri)
            
            val newFile = GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.setDisplayNameAsync(newName, GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    gfile.setDisplayNameFinish(result)
                }
            )
        newFile?.uri ?: uri
    }

    override suspend fun createLink(targetUri: String, linkUri: String): Result<String> = withVfsErrorHandling(linkUri) {
        val linkFile = File.newForUri(linkUri)
        val target = if (targetUri.startsWith("file://")) targetUri.removePrefix("file://") else targetUri
        
        GioCoroutineBridge.awaitGioAsync(
            block = { cancellable, callback ->
                linkFile.makeSymbolicLinkAsync(target, GLib.PRIORITY_DEFAULT, cancellable, callback)
            },
            finish = { result ->
                linkFile.makeSymbolicLinkFinish(result)
            }
        )
        linkUri
    }

    override suspend fun extractArchive(archiveUri: String, destDirUri: String): Result<String> = withVfsErrorHandling(archiveUri) {
        val archivePath = if (archiveUri.startsWith("file://")) archiveUri.removePrefix("file://") else archiveUri
        val destPath = if (destDirUri.startsWith("file://")) destDirUri.removePrefix("file://") else destDirUri
        
        val process = when {
            archivePath.endsWith(".zip", ignoreCase = true) -> 
                ProcessBuilder("unzip", "-o", archivePath, "-d", destPath).start()
            archivePath.endsWith(".tar.gz", ignoreCase = true) || archivePath.endsWith(".tgz", ignoreCase = true) -> 
                ProcessBuilder("tar", "-xzf", archivePath, "-C", destPath).start()
            archivePath.endsWith(".tar.xz", ignoreCase = true) -> 
                ProcessBuilder("tar", "-xJf", archivePath, "-C", destPath).start()
            archivePath.endsWith(".tar", ignoreCase = true) -> 
                ProcessBuilder("tar", "-xf", archivePath, "-C", destPath).start()
            else -> throw UnsupportedOperationException("Unsupported archive type: $archiveUri")
        }
        
        val exitCode = withContext(Dispatchers.IO) { process.waitFor() }
        if (exitCode != 0) {
            throw Exception("Extraction failed with exit code $exitCode")
        }
        destDirUri
    }

    override suspend fun compressArchive(sourceUris: List<String>, destArchiveUri: String): Result<String> = withVfsErrorHandling(destArchiveUri) {
        val destPath = if (destArchiveUri.startsWith("file://")) destArchiveUri.removePrefix("file://") else destArchiveUri
        val sourcePaths = sourceUris.map { if (it.startsWith("file://")) it.removePrefix("file://") else it }
        
        val process = when {
            destPath.endsWith(".zip", ignoreCase = true) -> {
                val cmd = mutableListOf("zip", "-r", destPath)
                cmd.addAll(sourcePaths)
                ProcessBuilder(cmd).start()
            }
            destPath.endsWith(".tar.gz", ignoreCase = true) || destPath.endsWith(".tgz", ignoreCase = true) -> {
                val cmd = mutableListOf("tar", "-czf", destPath)
                cmd.addAll(sourcePaths)
                ProcessBuilder(cmd).start()
            }
            destPath.endsWith(".tar.xz", ignoreCase = true) -> {
                val cmd = mutableListOf("tar", "-cJf", destPath)
                cmd.addAll(sourcePaths)
                ProcessBuilder(cmd).start()
            }
            destPath.endsWith(".tar", ignoreCase = true) -> {
                val cmd = mutableListOf("tar", "-cf", destPath)
                cmd.addAll(sourcePaths)
                ProcessBuilder(cmd).start()
            }
            else -> throw UnsupportedOperationException("Unsupported archive type: $destArchiveUri")
        }
        
        val exitCode = withContext(Dispatchers.IO) { process.waitFor() }
        if (exitCode != 0) {
            throw Exception("Compression failed with exit code $exitCode")
        }
        destArchiveUri
    }

    override suspend fun mountEnclosingVolume(uri: String): Result<Unit> = withVfsErrorHandling(uri) {
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
    }

    override suspend fun unmount(uri: String): Result<Unit> = withVfsErrorHandling(uri) {
        val gfile = File.newForUri(uri)
            val mount = gfile.findEnclosingMount(null) 
                ?: throw Exception("No enclosing mount found for $uri")
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    mount.unmountWithOperation(org.gnome.gio.MountUnmountFlags.NONE, null, cancellable, callback)
                },
                finish = { result ->
                    mount.unmountWithOperationFinish(result)
                }
            )
    }

    override suspend fun trash(job: FileJob, recoverTrashUri: Boolean): Result<String> = withVfsErrorHandling(job.source) {
        val gfile = File.newForUri(job.source)
        
        GioCoroutineBridge.awaitGioAsync(
            block = { cancellable, callback ->
                gfile.trashAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
            },
            finish = { result ->
                gfile.trashFinish(result)
            }
        )
        
        if (!recoverTrashUri) {
            return@withVfsErrorHandling ""
        }
        
        // RECOVERY: Find the actual trash URI by matching original path
        // Since GIO doesn't return the trash URI, we have to find it.
        val trashItems = listTrash().getOrThrow()
        val matchingItem = trashItems.find { it.originalPath == job.source }
            ?: throw Exception("Could not find trashed item in trash:///")
        
        matchingItem.trashPath
    }

    override suspend fun delete(job: FileJob): Result<Unit> = withVfsErrorHandling(job.source) {
        val gfile = File.newForUri(job.source)
            
            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gfile.deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result ->
                    gfile.deleteFinish(result)
                }
            )
    }

    override suspend fun executeInverse(payload: UndoAction): Result<Unit> = withVfsErrorHandling {
        when (payload) {
            is UndoAction.TransferUndo -> {
                // Transfer undo: delete destinations (for copy/link) or move back (for move)
                if (payload.sources != null) {
                    // Move-back: move destinations back to original source URIs
                    for (i in payload.destinations.indices) {
                        val destUri = payload.destinations[i]
                        val originalUri = payload.sources[i]
                        
                        val destFile = File.newForUri(destUri)
                        val finalDest = File.newForUri(originalUri)
                        
                        GioCoroutineBridge.awaitGioAsync(
                            block = { cancellable, callback ->
                                destFile.moveAsync(finalDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                            },
                            finish = { result ->
                                destFile.moveFinish(result)
                            }
                        )
                    }
                } else {
                    // Copy/Link undo: delete destinations
                    for (destUri in payload.destinations) {
                        val destFile = File.newForUri(destUri)
                        GioCoroutineBridge.awaitGioAsync(
                            block = { cancellable, callback ->
                                destFile.deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                            },
                            finish = { result ->
                                destFile.deleteFinish(result)
                            }
                        )
                    }
                }
            }
            is UndoAction.TrashUndo -> {
                // Trash undo: restore from trash
                for (i in payload.trashedUris.indices) {
                    val trashUri = payload.trashedUris[i]
                    val originalUri = payload.originalUris.getOrNull(i) ?: continue
                    restoreFromTrash(trashUri, originalUri).getOrThrow()
                }
            }
            is UndoAction.CreateUndo -> {
                // Create undo: delete the created item
                val destFile = File.newForUri(payload.createdUri)
                GioCoroutineBridge.awaitGioAsync(
                    block = { cancellable, callback ->
                        destFile.deleteAsync(GLib.PRIORITY_DEFAULT, cancellable, callback)
                    },
                    finish = { result ->
                        destFile.deleteFinish(result)
                    }
                )
            }
            is UndoAction.RenameUndo -> {
                // Rename undo: rename back to original name
                val currentFile = File.newForUri(payload.currentUri)
                GioCoroutineBridge.awaitGioAsync(
                    block = { cancellable, callback ->
                        currentFile.setDisplayNameAsync(payload.originalName, GLib.PRIORITY_DEFAULT, cancellable, callback)
                    },
                    finish = { result ->
                        currentFile.setDisplayNameFinish(result)
                    }
                )
            }
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
                        val fileInfo = GioTypeMappers.toImbricFileInfo(child, info)
                        
                        // Apply filters
                        val matchesMime = query.mimeFilter == null || fileInfo.mimeType.startsWith(query.mimeFilter)
                        val matchesDateRange = (query.modifiedAfter == null || (fileInfo.modifiedTime?.toEpochMilliseconds() ?: 0) >= query.modifiedAfter) &&
                                               (query.modifiedBefore == null || (fileInfo.modifiedTime?.toEpochMilliseconds() ?: Long.MAX_VALUE) <= query.modifiedBefore)
                        val matchesSizeRange = (query.minSize == null || fileInfo.size >= query.minSize) &&
                                               (query.maxSize == null || fileInfo.size <= query.maxSize)
                        
                        if (matchesMime && matchesDateRange && matchesSizeRange) {
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
        currentInfo = enrichImageMetadata(currentInfo)
        currentInfo = enrichDesktopMetadata(currentInfo)
        currentInfo
    }

    private suspend fun enrichImageMetadata(info: FileInfo): FileInfo {
        val mime = info.mimeType.lowercase()
        val isImage = mime.startsWith("image/") || mime.endsWith("/webp") || mime.endsWith("/heic") || mime.endsWith("/avif") || mime.endsWith("/jxl")
        
        if (!info.isDirectory && isImage) {
            val bytesResult = readHeader(info.uri, 65536)
            if (bytesResult.isSuccess) {
                val bytes = bytesResult.getOrThrow()
                var width = 0
                var height = 0
                
                // 1. Try Skia Codec first (extremely fast, pure Java/Kotlin, no native overhead)
                try {
                    val data = org.jetbrains.skia.Data.makeFromBytes(bytes)
                    val codec = org.jetbrains.skia.Codec.makeFromData(data)
                    if (codec != null) {
                        width = codec.width
                        height = codec.height
                    }
                } catch (e: Exception) {
                    // Skia failed or format not supported (e.g. JXL in pre-built Skiko)
                }
                
                // 2. Fall back to native PixbufLoader if Skia failed
                if (width <= 0 || height <= 0) {
                    try {
                        val loader = PixbufLoader()
                        loader.onSizePrepared { w, h ->
                            width = w
                            height = h
                        }
                        loader.write(bytes)
                        try { loader.close() } catch (e: Exception) { }
                    } catch (e: Exception) {
                        // Ignore parsing errors for partial/corrupt images
                    }
                }
                
                if (width > 0 && height > 0) {
                    val newAttrs = mapOf(
                        "std::dimensions" to "${width}x${height}",
                        "std::aspect-ratio" to width.toDouble() / height
                    )
                    return info.copy(attributes = info.attributes + newAttrs)
                }
            }
        }
        return info
    }

    private suspend fun enrichDesktopMetadata(info: FileInfo): FileInfo {
        var currentInfo = info
        if (currentInfo.name.endsWith(".desktop")) {
            val bytesResult = readHeader(currentInfo.uri, 1024 * 1024) // up to 1MB
            if (bytesResult.isSuccess) {
                val bytes = bytesResult.getOrThrow()
                try {
                    val keyFile = KeyFile()
                    // Convert bytes to string (assuming UTF-8 for desktop files)
                    val content = String(bytes)
                    if (keyFile.loadFromData(content, content.length.toLong(), KeyFileFlags.NONE)) {
                        val group = "Desktop Entry"
                        if (keyFile.hasGroup(group)) {
                            val newAttrs = mutableMapOf<String, Any?>()
                            try {
                                val type = keyFile.getString(group, "Type")
                                newAttrs["desktop::type"] = type
                                
                                val name = keyFile.getString(group, "Name")
                                if (name != null) {
                                    currentInfo = currentInfo.copy(displayName = name)
                                }
                                
                                val icon = keyFile.getString(group, "Icon")
                                if (icon != null) {
                                    currentInfo = currentInfo.copy(iconName = icon)
                                }
                                
                                if (keyFile.hasKey(group, "Exec")) {
                                    newAttrs["desktop::exec"] = keyFile.getString(group, "Exec")
                                }
                                if (keyFile.hasKey(group, "URL")) {
                                    newAttrs["desktop::url"] = keyFile.getString(group, "URL")
                                }
                            } catch (e: Exception) {
                                // Missing keys are fine
                            }
                            if (newAttrs.isNotEmpty()) {
                                currentInfo = currentInfo.copy(attributes = currentInfo.attributes + newAttrs)
                            }
                        }
                    }
                } catch (e: Exception) {
                    // Parsing failed
                }
            }
        }
        return currentInfo
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

    override suspend fun getUsage(uri: String): Result<DiskUsage?> = withVfsErrorHandling(uri) {
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

    private fun translateError(e: Exception, uri: String = ""): VfsError {
        return when {
            e is VfsError -> e
            e is org.gnome.gio.IOException -> when (e.enum) {
                org.gnome.gio.IOErrorEnum.EXISTS -> VfsError.AlreadyExists(uri)
                org.gnome.gio.IOErrorEnum.NOT_FOUND -> VfsError.NotFound(uri)
                org.gnome.gio.IOErrorEnum.WOULD_RECURSE -> VfsError.WouldRecurse(uri)
                org.gnome.gio.IOErrorEnum.PERMISSION_DENIED -> VfsError.PermissionDenied(uri)
                org.gnome.gio.IOErrorEnum.NO_SPACE -> VfsError.NoSpace(uri)
                org.gnome.gio.IOErrorEnum.READ_ONLY -> VfsError.ReadOnly(uri)
                org.gnome.gio.IOErrorEnum.CANCELLED -> VfsError.Cancelled(uri)
                org.gnome.gio.IOErrorEnum.NOT_SUPPORTED -> VfsError.NotSupported(uri)
                org.gnome.gio.IOErrorEnum.IS_DIRECTORY -> VfsError.IsDirectory(uri)
                org.gnome.gio.IOErrorEnum.NOT_DIRECTORY -> VfsError.NotDirectory(uri)
                org.gnome.gio.IOErrorEnum.WOULD_BLOCK -> VfsError.Busy(uri)
                else -> VfsError.IoError(uri, e.message ?: "Unknown I/O error", e)
            }
            e is org.javagi.base.GErrorException -> when (e.code) {
                0 -> VfsError.IoError(uri, e.message ?: "I/O error", e)
                1 -> VfsError.NotFound(uri)
                2 -> VfsError.AlreadyExists(uri)
                3 -> VfsError.PermissionDenied(uri)
                14 -> VfsError.NoSpace(uri)
                15 -> VfsError.ReadOnly(uri)
                18 -> VfsError.IsDirectory(uri)
                20 -> VfsError.NotDirectory(uri)
                25 -> VfsError.WouldRecurse(uri)
                else -> VfsError.IoError(uri, e.message ?: "Unknown error", e)
            }
            e is java.util.concurrent.CancellationException -> VfsError.Cancelled(uri)
            else -> VfsError.IoError(uri, e.message ?: "Unknown error", e)
        }
    }

    /**
     * Runs a block on the IO dispatcher and translates any GIO errors to [VfsError].
     * Inlined to avoid lambda allocation overhead.
     */
    private suspend inline fun <T> withVfsErrorHandling(uri: String = "", crossinline block: suspend () -> T): Result<T> = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        try {
            Result.success(block())
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            Result.failure(translateError(e, uri))
        }
    }
}