package com.imbric.core.ifs.backends.gio

import com.imbric.core.ifs.BackendCapabilities
import com.imbric.core.ifs.LatencyProfile
import com.imbric.core.ifs.Locality
import com.imbric.core.ifs.FileAction
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.ifs.contracts.SearchContract
import com.imbric.core.models.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.*
import java.io.BufferedReader
import java.io.InputStreamReader

open class GioSearchBackend(private val fallback: BackendContract = GioBackend()) : BackendContract, SearchContract {
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

    override suspend fun list(uri: String, sortKey: SortKey): List<FileEntry> {
        // search:///query?root=...&mime=...
        val text = uri.substringAfter("search:///", "").substringBefore("?")
        val params = uri.substringAfter("?", "").split("&").associate {
            val parts = it.split("=")
            if (parts.size == 2) parts[0] to parts[1] else it to ""
        }
        val root = params["root"]?.let { java.net.URLDecoder.decode(it, "UTF-8") } ?: "file:///"
        val mime = params["mime"]

        // search() streams in batches (see [SEARCH_BATCH_SIZE]) so a broad query never
        // buffers the whole result set before the first emission. list() must still return
        // the *complete* result list, so it re-aggregates the batches rather than taking
        // the first one.
        return search(com.imbric.core.models.VfsQuery(text = text, rootUri = root, mimeFilter = mime))
            .toList()
            .flatten()
    }

    override fun search(query: com.imbric.core.models.VfsQuery): Flow<List<FileEntry>> = flow {
        if (query.text.isBlank()) {
            emit(emptyList())
            return@flow
        }

        // Pending results, flushed downstream every [SEARCH_BATCH_SIZE] entries. Mirrors
        // GioBackend.search so a Tracker3 hit stream reaches the UI progressively instead of
        // being retained in full until tracker3 exits.
        val batch = mutableListOf<FileEntry>()

        // 1. Try Tracker3
        var trackerSuccess = false
        var scanned = 0

        try {
            // runTrackerSearch might throw immediately, or might throw during collection
            runTrackerSearch(query).collect { uri ->
                scanned++
                if (scanned % 100 == 0) {
                    query.onScanned?.invoke(scanned)
                    kotlinx.coroutines.yield()
                }

                // Robust root check: must be root itself or a child of root
                val isMatch = uri == query.rootUri || uri.startsWith("${query.rootUri.removeSuffix("/")}/")
                if (isMatch) {
                    val info = fallback.getMetadata(uri).getOrNull()
                    if (info != null) {
                        // Filter by hidden status and MIME
                        if (!query.includeHidden && info.isVisiblyHidden()) return@collect
                        if (query.mimeFilter == null || info.mimeType.startsWith(query.mimeFilter)) {
                            batch.add(info)
                            if (batch.size >= SEARCH_BATCH_SIZE) {
                                emit(batch.toList())
                                batch.clear()
                            }
                        }
                    }
                }
                trackerSuccess = true
            }
            if (trackerSuccess) {
                query.onScanned?.invoke(scanned)
            }
        } catch (e: CancellationException) {
            // emit() below suspends: a collector that stops early (take/firstOrNull) or a
            // cancelled scope must abort the search, not be mistaken for a Tracker failure
            // and retried through the (much slower) manual walk.
            throw e
        } catch (e: Exception) {
            trackerSuccess = false
        }

        if (!trackerSuccess) {
            // 2. Fallback to manual walk — re-batch the fallback's own batches so the
            // downstream batch size stays uniform regardless of which path produced it.
            (fallback as? SearchContract)?.search(query)?.collect { incoming ->
                batch.addAll(incoming)
                if (batch.size >= SEARCH_BATCH_SIZE) {
                    emit(batch.toList())
                    batch.clear()
                }
            }
        }

        if (batch.isNotEmpty()) {
            emit(batch.toList())
        }
    }

    // Visible for testing
    internal open fun runTrackerSearch(query: com.imbric.core.models.VfsQuery): Flow<String> = callbackFlow {
        val flag = if (query.contentSearch) "-c" else "-f"
        // redirectErrorStream(true): tracker3 writes progress/diagnostics to stderr. If that
        // pipe is never drained it fills at 64KiB and blocks the child forever, wedging the
        // search even without any cancellation. Merging it into stdout makes the single reader
        // below drain both; non-`file://` lines are filtered out anyway.
        val process = ProcessBuilder("tracker3", "search", "--disable-color", flag, "--", query.text)
            .redirectErrorStream(true)
            .start()

        // reader.readLine() is a blocking call with no cancellation checkpoint. Running it on
        // the collector's dispatcher parks a thread for the child's whole lifetime; the
        // Listing pool is only 8 wide, so a handful of cancelled searches would stall every
        // listing in the app. A dedicated IO job keeps the collector's thread free, and the
        // awaitClose/destroyForcibly pair below reaps the child the instant the collector
        // goes away.
        val readerJob = launch(Dispatchers.IO) {
            try {
                BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                    var line = reader.readLine()
                    while (line != null && isActive) {
                        val trimmed = line.trim()
                        if (trimmed.startsWith("file://")) {
                            trySend(trimmed)
                        }
                        line = reader.readLine()
                    }
                }
                val exit = process.waitFor()
                if (exit != 0) {
                    close(Exception("Tracker search failed with exit code ${process.exitValue()}"))
                } else {
                    close()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                close(e)
            }
        }

        // Belt and braces: awaitClose covers collector cancellation/completion, this covers
        // the reader job dying for any other reason.
        readerJob.invokeOnCompletion { process.destroyForcibly() }

        awaitClose {
            readerJob.cancel()
            process.destroyForcibly()
        }
    }

    // Delegate other methods to fallback or fail
    override suspend fun getMetadata(uri: String): Result<FileInfo> = fallback.getMetadata(uri)
    override fun exists(uri: String): Boolean = fallback.exists(uri)
    override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = fallback.readHeader(uri, size)

    private companion object {
        /** Matches GioBackend.search's flush interval. */
        const val SEARCH_BATCH_SIZE = 50
    }
}
