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
    val isSymlink: Boolean
        get() = false
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
         * GIO attributes for listing, by sort key. `time::modified` is in the shared
         * base for EVERY key: re-sort is local (no fresh enumeration), and onActive's
         * fingerprint needs mtime to catch a same-size in-place edit.
         * `time::modified-nsec` rides along so the mapper builds a sub-second Instant —
         * whole-second truncation would hide a same-second, same-size rewrite from dedup.
         * `standard::is-symlink` lets list() resolve link-to-dirs with one follow-query
         * (Nautilus parity: a linked dir lists as a dir).
         */
        fun listingAttributesFor(sortKey: SortKey): String {
            val base = "standard::name,standard::type,standard::is-hidden,standard::size,standard::content-type,standard::is-symlink,time::modified,time::modified-nsec"
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
         * Bounded (64) LRU of compiled globs — patterns are user-typed, so the cache
         * must not grow. Reachable from any thread (UI or IO collectors; public
         * [matches]), and access-order touches require the synchronized wrapper.
         * Get-or-compile-put runs under the cache monitor so racers share one compile
         * and observe the identical (===) instance.
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
            synchronized(globCache) {
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
}
