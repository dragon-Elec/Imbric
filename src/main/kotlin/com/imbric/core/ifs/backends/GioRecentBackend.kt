@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.ifs.*
import com.imbric.core.models.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import org.gnome.gtk.Gtk
import org.gnome.gtk.RecentManager
import org.gnome.gio.File
import org.gnome.gio.FileQueryInfoFlags
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

class GioRecentBackend : IOBackend {
    init {
        org.gnome.gtk.Gtk.`javagi$ensureInitialized`()
        try {
            if (!Gtk.isInitialized()) {
                Gtk.init()
            }
        } catch (e: Exception) {
            // Ignore if already initialized
        }
    }

    override val scheme: String = "recent"
    override val displayName: String = "Recent Files"

    override fun getCapabilities(uri: String) = BackendCapabilities(
        locality = Locality.VIRTUAL,
        latencyProfile = LatencyProfile.LOW,
        supportsTrash = false,
        supportsSymlinks = false
    )

    override suspend fun canPerform(action: FileAction, uri: String): Boolean = false

    override fun list(uri: String): Flow<FileInfo> = flow {
        val rm = RecentManager.getDefault()
        val items = rm.items ?: return@flow
        
        val queryAttributes = "standard::*,time::*,unix::*,owner::*,access::*,trash::*"
        for (item in items) {
            if (item == null) continue
            val itemUri = item.uri ?: continue
            
            val gfile = File.newForUri(itemUri)
            try {
                if (gfile.queryExists(null)) {
                    val info = gfile.queryInfo(queryAttributes, FileQueryInfoFlags.NONE, null)
                    emit(GioTypeMappers.toImbricFileInfo(gfile, info, "recent"))
                }
            } catch (e: Exception) {
                // Skip on error
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun getMetadata(uri: String): Result<FileInfo> {
        return Result.failure(UnsupportedOperationException("getMetadata not supported for recent:///"))
    }

    override fun exists(uri: String): Boolean = uri.startsWith("recent://")

    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = Result.failure(UnsupportedOperationException())

    override suspend fun copy(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.emptyFlow()
    override suspend fun move(job: FileJob): Flow<TransferProgress> = kotlinx.coroutines.flow.emptyFlow()
    override suspend fun trash(job: FileJob): Result<String> = Result.failure(UnsupportedOperationException())
    override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = Result.failure(UnsupportedOperationException())
    override suspend fun delete(job: FileJob): Result<Unit> = Result.failure(UnsupportedOperationException())
    override suspend fun createFolder(parentUri: String, name: String): Result<String> = Result.failure(UnsupportedOperationException())
    override suspend fun createFile(parentUri: String, name: String): Result<String> = Result.failure(UnsupportedOperationException())
    override suspend fun rename(uri: String, newName: String): Result<String> = Result.failure(UnsupportedOperationException())

    override suspend fun addToRecent(uri: String, mimeType: String?): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val rm = RecentManager.getDefault()
            rm.addItem(uri)
            Unit
        }
    }

    override suspend fun removeFromRecent(uri: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val rm = RecentManager.getDefault()
            rm.removeItem(uri)
            Unit
        }
    }

    override suspend fun purgeRecent(olderThanMs: Long): Result<Int> = withContext(Dispatchers.IO) {
        runCatching {
            val rm = RecentManager.getDefault()
            rm.purgeItems()
        }
    }
}