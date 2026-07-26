@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs

import com.imbric.core.ifs.contracts.*
import com.imbric.core.models.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

@Deprecated("Use BackendContract + capability contracts directly. Will be removed in Phase 0 Pass 2.")
interface IOBackend : BackendContract, WriteContract, TrashContract, SearchContract, MountContract, ThumbnailContract, RecentContract, ArchiveContract, UndoContract {

    override suspend fun getThumbnailPath(uri: String): String? {
        return getMetadata(uri).getOrNull()?.thumbnailPath
    }

    override fun search(query: VfsQuery): Flow<List<FileEntry>> = flow {
        val stack = ArrayDeque<Pair<String, Int>>()
        stack.add(query.rootUri to 0)
        val allMatches = mutableListOf<FileEntry>()

        while (stack.isNotEmpty()) {
            val (dirUri, depth) = stack.removeLast()
            if (depth > query.maxDepth) continue

            try {
                val items = list(dirUri)
                for (info in items) {
                    // 1. Recurse
                    if (info.isDirectory && query.recursive) {
                        stack.add(info.uri to depth + 1)
                    }

                    // 2. Filter
                    if (!query.includeHidden && info.isVisiblyHidden()) continue
                    val matchesText = query.text.isEmpty() || info.name.contains(query.text, ignoreCase = true)
                    if (!matchesText) continue
                    val matchesMime = query.mimeFilter == null || info.mimeType.startsWith(query.mimeFilter)
                    if (!matchesMime) continue

                    val mtime = info.modifiedTime?.toEpochMilliseconds()
                    val matchesDate = (query.modifiedAfter == null || (mtime != null && mtime >= query.modifiedAfter)) &&
                        (query.modifiedBefore == null || (mtime != null && mtime <= query.modifiedBefore))
                    if (!matchesDate) continue

                    val matchesSize = (query.minSize == null || info.size >= query.minSize) &&
                        (query.maxSize == null || info.size <= query.maxSize)
                    if (!matchesSize) continue

                    if (query.starredOnly && (info !is FileInfo || !info.isStarred)) continue

                    allMatches.add(info)
                }
            } catch (e: Exception) {
                // Skip unreadable dirs
            }
        }
        emit(allMatches)
    }

    override suspend fun getTrashBackend(registry: BackendRegistry): IOBackend? {
        val rootUri = "$scheme:///"
        val backend = registry.getIo(rootUri)
        return if (backend != null && backend.getCapabilities(rootUri).supportsTrash) backend else null
    }
}
