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
    
    // Virtual timestamps
    val trashTime: Instant? = null,
    val recency: Instant? = null,

    // Behavioral flags
    val isStarred: Boolean = false,

    // Activation
    val activationUri: String? = null,
    
    // Location Flags
    val isInTrash: Boolean = false,
    val isInRecent: Boolean = false,
    val isRemote: Boolean = false,
    
    // Mount Capabilities
    val canMount: Boolean = false,
    val canUnmount: Boolean = false,
    val canEject: Boolean = false,
    
    // Security
    /** SELinux security context string (e.g., "unconfined_u:object_r:user_home_t:s0"). */
    val selinuxContext: String? = null,
    
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
        return compileGlob(pattern).matches(name)
    }

    val extension: String
        get() = name.substringAfterLast('.', "")

    val isEmptyDirectory: Boolean
        get() = isDirectory && childCount == 0

    /** Computed property — derived from mimeType. True if file is an archive (zip, tar, 7z, etc.). */
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

    /** Computed property — derived from mimeType + activationUri. True if file can be launched/executed. */
    val isLaunchable: Boolean
        get() = !isDirectory && (
                mimeType == "application/x-desktop" ||
                mimeType == "application/x-executable" ||
                isExecutable ||
                activationUri != null)

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

    // --- Metadata accessors (Phase 5) ---
    
    /** Gets a string value from the GNOME metadata namespace (e.g., "nautilus-tags-starred"). */
    fun getMetadata(key: String): String? = attributes["metadata::$key"] as? String

    /** Gets an integer value from the GNOME metadata namespace. */
    fun getMetadataInt(key: String): Int? = (attributes["metadata::$key"] as? Number)?.toInt()

    /** Gets a boolean value from the GNOME metadata namespace. */
    fun getMetadataBool(key: String): Boolean? = attributes["metadata::$key"] as? Boolean

    /** Gets all metadata keys that start with the given prefix. */
    fun getMetadataKeys(prefix: String = ""): List<String> {
        return attributes.keys
            .filter { it.startsWith("metadata::$prefix") }
            .map { it.removePrefix("metadata::") }
    }

    companion object {
        /** Sort by name (directories first, then files). */
        val SortByName = compareBy<FileInfo> { !it.isDirectory }.thenBy { it.name.lowercase() }

        /** Sort by size (directories first, then largest files). */
        val SortBySize = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.size }

        /** Sort by modification time (directories first, then newest files). */
        val SortByDate = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.modifiedTime }

        /** Sort by trash deletion time (newest deleted first). */
        val SortByTrashTime = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.trashTime }

        /** Sort by recency (most recently accessed first). */
        val SortByRecency = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.recency }

        /**
         * Compiles a glob pattern into a [Regex].
         * Supports `*` (any characters) and `?` (single character).
         * Compiled once and reused for bulk filtering in [DirState.matchPattern].
         *
         * Manually escapes all regex-special characters, then converts glob wildcards.
         * This prevents [java.util.regex.PatternSyntaxException] for patterns like `report(v2).*`.
         */
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
