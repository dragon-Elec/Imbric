@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.time.Instant
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid
import java.util.Collections

/** Sort key for directory listing. UI sets this, DirState adapts attribute fetching. */
enum class SortKey {
    NAME, SIZE, MODIFIED, TYPE
}

sealed interface FileEntry {
    val name: String
    val uri: String
    val path: String
    val pathType: PathType
    val isDirectory: Boolean
    val size: Long
    val mimeType: String
    val modifiedTime: Instant?
    val isHidden: Boolean
    val iconName: String?
    val isInTrash: Boolean
    val isInRecent: Boolean
    val isRemote: Boolean
    
    val displayName: String
        get() = name

    fun isVisiblyHidden(showHiddenFiles: Boolean = false): Boolean {
        if (showHiddenFiles) return false
        return isHidden || name.startsWith(".")
    }

    fun shouldShow(showHiddenFiles: Boolean = false): Boolean {
        return !isVisiblyHidden(showHiddenFiles)
    }

    fun matches(pattern: String): Boolean {
        if (pattern.isEmpty() || pattern == "*") return true
        return FileEntry.compileGlob(pattern).matches(name)
    }

    val extension: String
        get() = name.substringAfterLast('.', "")

    val isArchive: Boolean
        get() {
            if (isDirectory) return false
            return isArchiveMimeType(mimeType.lowercase())
        }

    val humanReadableSize: String
        get() {
            if (isDirectory) return ""
            if (size <= 0) return "0 B"
            val units = arrayOf("B", "KB", "MB", "GB", "TB")
            val digitGroups = (Math.log10(size.toDouble()) / Math.log10(1024.0)).toInt()
            return String.format("%.1f %s", size / Math.pow(1024.0, digitGroups.toDouble()), units[digitGroups])
        }


    val isEmptyDirectory: Boolean
        get() = false // Default for listing, overridden in FileInfo

    val isLaunchable: Boolean
        get() = !isDirectory && (
                mimeType == "application/x-desktop" ||
                mimeType == "application/x-executable")

    companion object {
        /**
         * Archive MIME predicates, shared by [isArchive] and the UI icon path.
         *
         * The input must already be lowercased — callers lowercase once and
         * reuse the value (e.g. for icon dispatch) to avoid a second
         * [String.lowercase] per row. Directories are the caller's concern:
         * [isArchive] rules them out before delegating here.
         */
        fun isArchiveMimeType(mimeLowercase: String): Boolean =
            mimeLowercase.startsWith("application/zip") ||
                    mimeLowercase.startsWith("application/x-tar") ||
                    mimeLowercase.startsWith("application/x-7z") ||
                    mimeLowercase.startsWith("application/x-rar") ||
                    mimeLowercase.startsWith("application/x-xz") ||
                    mimeLowercase.startsWith("application/gzip") ||
                    mimeLowercase.startsWith("application/x-bzip2") ||
                    mimeLowercase.startsWith("application/x-compressed-tar") ||
                    mimeLowercase.endsWith("+zip") ||
                    mimeLowercase.endsWith("+tar") ||
                    mimeLowercase.endsWith("+xz") ||
                    mimeLowercase.endsWith("+bzip2") ||
                    mimeLowercase.endsWith("+gzip") ||
                    mimeLowercase.endsWith("+rar") ||
                    mimeLowercase.endsWith("+7z")

        val SortByName = compareBy<FileEntry> { !it.isDirectory }.thenBy { it.name.lowercase() }
        val SortBySize = compareBy<FileEntry> { !it.isDirectory }.thenByDescending { it.size }
        val SortByDate = compareBy<FileEntry> { !it.isDirectory }.thenByDescending { it.modifiedTime }

        /**
         * Returns the GIO attributes needed for listing, based on the sort key.
         *
         * `time::modified` is part of the shared base and is therefore fetched for EVERY
         * sort key, not just [SortKey.MODIFIED]: [SortByDate] compares [FileEntry.modifiedTime]
         * directly, so a listing produced under NAME/SIZE/TYPE could never be re-sorted by
         * date locally, and `onActive`'s change fingerprint needs mtime to detect an in-place
         * edit that keeps the byte count identical. The cost is a single extra attribute
         * token in the enumerate string; the benefit is that DirState.setSortKey can re-sort
         * the cached listing without paying for a fresh GIO enumeration.
         *
         * `standard::is-symlink` lets GioBackend.list() detect symlinks and
         * resolve the target's type with one follow-query, so a symlink whose
         * target is a directory lists as a directory (Nautilus parity).
         */
        fun listingAttributesFor(sortKey: SortKey): String {
            val base = "standard::name,standard::type,standard::is-hidden,standard::size,standard::content-type,standard::is-symlink,time::modified"
            return when (sortKey) {
                SortKey.NAME -> base
                SortKey.SIZE -> base
                SortKey.MODIFIED -> base
                SortKey.TYPE -> base
            }
        }

        /** Returns a Comparator for the given sort key. */
        fun comparatorFor(sortKey: SortKey): Comparator<FileEntry> = when (sortKey) {
            SortKey.NAME -> SortByName
            SortKey.SIZE -> SortBySize
            SortKey.MODIFIED -> SortByDate
            SortKey.TYPE -> SortByName // fallback to name
        }

        /** Max compiled patterns retained in [globCache]. Patterns are user-typed globs, so the cache must stay bounded. */
        private const val GLOB_CACHE_MAX = 64

        /**
         * LRU cache of compiled globs keyed by pattern string.
         *
         * Synchronized because [compileGlob] is reachable from any thread:
         * DirState.matchPattern runs on StateFlow collectors (UI or IO
         * dispatchers) and FileEntry.matches is a public interface method.
         * All map access — including access-order touches — goes through the
         * synchronized wrapper, which access-order LinkedHashMaps require.
         * A benign race (two threads compiling the same pattern at once)
         * only wastes one compile; both produce equivalent Regexes.
         */
        private val globCache: MutableMap<String, Regex> =
            Collections.synchronizedMap(
                object : LinkedHashMap<String, Regex>(GLOB_CACHE_MAX, 0.75f, true) {
                    override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Regex>): Boolean =
                        size > GLOB_CACHE_MAX
                }
            )

        /** Constant wildcard regex for the empty/"*" patterns — compiled once at class load. */
        private val WILDCARD_GLOB: Regex = Regex(".*")

        fun compileGlob(pattern: String): Regex {
            if (pattern.isEmpty() || pattern == "*") return WILDCARD_GLOB
            globCache[pattern]?.let { return it }
            val regexStr = buildString(pattern.length * 2) {
                for (c in pattern) {
                    when (c) {
                        '*' -> append(".*")
                        '?' -> append('.')
                        '.', '(', ')', '[', ']', '{', '}', '+', '^', '$', '|', '\\' -> {
                            append('\\')
                            append(c)
                        }
                        else -> append(c)
                    }
                }
            }
            val regex = Regex(regexStr, RegexOption.IGNORE_CASE)
            globCache[pattern] = regex
            return regex
        }
    }
}
