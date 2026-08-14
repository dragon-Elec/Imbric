package com.imbric.core.ifs.backends.gio

import com.imbric.core.ifs.*
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.contracts.RecentContract
import com.imbric.core.ifs.backends.gio.support.GioTypeMappers
import com.imbric.core.models.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import org.gnome.gio.File
import org.gnome.gio.FileQueryInfoFlags
import org.gnome.glib.BookmarkFile
import org.gnome.glib.GLib
import mu.KotlinLogging
import java.nio.file.Paths

private val recentLogger = KotlinLogging.logger { }

class GioRecentBackend : BackendContract, RecentContract {
    override val scheme: String = "recent"
    override val displayName: String = "Recent Files"

    override fun getCapabilities(uri: String) = BackendCapabilities(
        locality = Locality.VIRTUAL,
        latencyProfile = LatencyProfile.LOW,
        supportsTrash = false,
        supportsSymlinks = false
    )

    override suspend fun canPerform(action: FileAction, uri: String): Boolean = false

    private fun getRecentFilePath(): String {
        val dataDir = GLib.getUserDataDir().toString()
        return Paths.get(dataDir, "recently-used.xbel").toString()
    }

    override suspend fun list(uri: String, sortKey: SortKey): List<FileEntry> {
        val bookmarkFile = BookmarkFile()
        try {
            bookmarkFile.loadFromFile(getRecentFilePath())
        } catch (e: Exception) {
            return emptyList()
        }

        val uris = bookmarkFile.uris ?: return emptyList()
        val queryAttributes = "standard::*,time::*,unix::*,owner::*,access::*,trash::*"
        val results = mutableListOf<FileEntry>()
        val skipped = mutableListOf<String>()

        for (itemUri in uris) {
            if (itemUri == null) continue

            val gfile = File.forUri(itemUri)
            try {
                val info = gfile.queryInfo(queryAttributes, FileQueryInfoFlags.NONE, null)
                results.add(GioTypeMappers.toImbricFileInfo(gfile, info, "recent"))
            } catch (e: Exception) {
                skipped += itemUri
            }
        }
        if (skipped.isNotEmpty()) {
            recentLogger.info { "Recent files: loaded ${results.size}, skipped ${skipped.size} missing entries" }
        }
        return results
    }

    override suspend fun getMetadata(uri: String): Result<FileInfo> {
        return Result.failure(UnsupportedOperationException("getMetadata not supported for recent:///"))
    }

    override fun exists(uri: String): Boolean = uri.startsWith("recent://")

    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = Result.failure(UnsupportedOperationException())

    override suspend fun addToRecent(uri: String, mimeType: String?): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val bookmarkFile = BookmarkFile()
            val path = getRecentFilePath()
            
            try {
                bookmarkFile.loadFromFile(path)
            } catch (e: Exception) {
                // Ignore load errors, we'll just create a new file
            }

            if (mimeType != null) {
                bookmarkFile.setMimeType(uri, mimeType)
            } else {
                bookmarkFile.setMimeType(uri, "application/octet-stream")
            }

            // Required by XBEL spec for the entry to be valid
            bookmarkFile.addApplication(uri, "Imbric", "imbric %u")
            
            bookmarkFile.toFile(path)
            Unit
        }
    }

    override suspend fun removeFromRecent(uri: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val path = getRecentFilePath()
            if (!java.io.File(path).exists()) {
                return@runCatching Unit
            }
            val bookmarkFile = BookmarkFile()
            bookmarkFile.loadFromFile(path)
            bookmarkFile.removeItem(uri)
            bookmarkFile.toFile(path)
            Unit
        }
    }

    override suspend fun purgeRecent(olderThanMs: Long): Result<Int> = withContext(Dispatchers.IO) {
        runCatching {
            val path = getRecentFilePath()
            if (!java.io.File(path).exists()) {
                return@runCatching 0
            }
            val bookmarkFile = BookmarkFile()
            bookmarkFile.loadFromFile(path)
            val uris = bookmarkFile.uris ?: return@runCatching 0
            var removed = 0
            
            for (uri in uris) {
                if (uri != null) {
                    bookmarkFile.removeItem(uri)
                    removed++
                }
            }
            
            if (removed > 0) {
                bookmarkFile.toFile(path)
            }
            removed
        }
    }
}