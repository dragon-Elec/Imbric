@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.time.Instant
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

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
            val m = mimeType.lowercase()
            return m.startsWith("application/zip") ||
                   m.startsWith("application/x-tar") ||
                   m.startsWith("application/x-7z") ||
                   m.startsWith("application/x-rar") ||
                   m.startsWith("application/x-xz") ||
                   m.startsWith("application/gzip") ||
                   m.startsWith("application/x-bzip2") ||
                   m.startsWith("application/x-compressed-tar") ||
                   m.endsWith("+zip") ||
                   m.endsWith("+tar") ||
                   m.endsWith("+xz") ||
                   m.endsWith("+bzip2") ||
                   m.endsWith("+gzip") ||
                   m.endsWith("+rar") ||
                   m.endsWith("+7z")
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
        val SortByName = compareBy<FileEntry> { !it.isDirectory }.thenBy { it.name.lowercase() }
        val SortBySize = compareBy<FileEntry> { !it.isDirectory }.thenByDescending { it.size }
        val SortByDate = compareBy<FileEntry> { !it.isDirectory }.thenByDescending { it.modifiedTime }

        /** Returns the GIO attributes needed for listing, based on the sort key. */
        fun listingAttributesFor(sortKey: SortKey): String {
            val base = "standard::name,standard::type,standard::is-hidden,standard::size,standard::content-type"
            return when (sortKey) {
                SortKey.NAME -> base
                SortKey.SIZE -> base
                SortKey.MODIFIED -> "$base,time::modified"
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

        fun compileGlob(pattern: String): Regex {
            if (pattern.isEmpty() || pattern == "*") return Regex(".*")
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
            return Regex(regexStr, RegexOption.IGNORE_CASE)
        }
    }
}
