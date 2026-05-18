@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlinx.datetime.Instant
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

data class FileInfo(
    val id: Uuid = Uuid.random(),
    /** Native identifier (Inode, Windows Handle, or Android DocumentID) for stable tracking across renames. */
    val nativeId: String? = null,
    val name: String,
    val path: String,
    val uri: String,
    val pathType: PathType = PathType.PHYSICAL,
    val displayName: String = name,
    val isDirectory: Boolean,
    val isSymlink: Boolean = false,
    val symlinkTarget: String? = null,
    val size: Long = 0L,
    val mimeType: String = "application/octet-stream",
    val modifiedTime: Instant? = null,
    val accessedTime: Instant? = null,
    val createdTime: Instant? = null,
    val isHidden: Boolean = false,
    val isReadable: Boolean = true,
    val isWritable: Boolean = true,
    val isExecutable: Boolean = false,
    val permissions: String = "",
    val owner: String = "",
    val group: String = "",
    val childCount: Int = 0,
    val iconName: String? = null,
    val thumbnailPath: String? = null,
    val backendId: String? = null,
    
    // Location Flags
    val isInTrash: Boolean = false,
    val isInRecent: Boolean = false,
    val isRemote: Boolean = false,
    
    // Mount Capabilities
    val canMount: Boolean = false,
    val canUnmount: Boolean = false,
    val canEject: Boolean = false,
    
    /** Extensible bag for native-specific metadata (e.g., GIO attributes, Windows ACLs, Android Scoped Storage tags). */
    val attributes: Map<String, Any?> = emptyMap()
) {
    /**
     * Returns true if the file should be hidden from the user by default.
     * Checks for leading dots and the native hidden flag.
     */
    fun isVisiblyHidden(showHiddenFiles: Boolean = false): Boolean {
        if (showHiddenFiles) return false
        return isHidden || name.startsWith(".")
    }

    /**
     * Returns true if the file should be shown in the UI.
     */
    fun shouldShow(showHiddenFiles: Boolean = false): Boolean {
        return !isVisiblyHidden(showHiddenFiles)
    }

    /**
     * Returns true if this file matches the given glob pattern.
     */
    fun matches(pattern: String): Boolean {
        if (pattern.isEmpty() || pattern == "*") return true
        // Escape dots FIRST, then replace wildcards — otherwise the dots inside `.*` get escaped
        val regex = pattern
            .replace(".", "\\.")   // escape literal dots
            .replace("*", ".*")    // glob * → regex .*
            .replace("?", ".")     // glob ? → regex .
            .toRegex(RegexOption.IGNORE_CASE)
        return regex.matches(name)
    }

    val extension: String
        get() = name.substringAfterLast('.', "")

    val isEmptyDirectory: Boolean
        get() = isDirectory && childCount == 0

    val permissionsString: String
        get() {
            if (permissions.isEmpty()) return ""
            val mode = permissions.toIntOrNull(8) ?: return ""
            val type = if (isDirectory) 'd' else if (isSymlink) 'l' else '-'
            
            fun rwx(m: Int): String = buildString {
                append(if (m and 4 != 0) 'r' else '-')
                append(if (m and 2 != 0) 'w' else '-')
                append(if (m and 1 != 0) 'x' else '-')
            }
            
            return "$type${rwx(mode shr 6)}${rwx(mode shr 3)}${rwx(mode)}"
        }

    val humanReadableSize: String
        get() {
            if (isDirectory) return ""
            if (size <= 0) return "0 B"
            val units = arrayOf("B", "KB", "MB", "GB", "TB")
            val digitGroups = (Math.log10(size.toDouble()) / Math.log10(1024.0)).toInt()
            return String.format("%.1f %s", size / Math.pow(1024.0, digitGroups.toDouble()), units[digitGroups])
        }

    companion object {
        /** Sort by name (directories first, then files). */
        val SortByName = compareBy<FileInfo> { !it.isDirectory }.thenBy { it.name.lowercase() }

        /** Sort by size (directories first, then largest files). */
        val SortBySize = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.size }

        /** Sort by modification time (directories first, then newest files). */
        val SortByDate = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.modifiedTime }
    }
}
