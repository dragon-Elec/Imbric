@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.time.Instant
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

data class FileInfo(
    val id: Uuid = Uuid.random(),
    /** Native identifier (Inode, Windows Handle, or Android DocumentID) for stable tracking across renames. */
    val nativeId: String? = null,
    override val name: String,
    override val path: String,
    override val uri: String,
    override val pathType: PathType = PathType.PHYSICAL,
    override val displayName: String = name,
    override val isDirectory: Boolean,
    val isSymlink: Boolean = false,
    val symlinkTarget: String? = null,
    override val size: Long = 0L,
    override val mimeType: String = "application/octet-stream",
    override val modifiedTime: Instant? = null,
    val accessedTime: Instant? = null,
    val createdTime: Instant? = null,
    override val isHidden: Boolean = false,
    val isReadable: Boolean = true,
    val isWritable: Boolean = true,
    val isExecutable: Boolean = false,
    val permissions: String = "",
    val owner: String = "",
    val group: String = "",
    val childCount: Int = 0,
    override val iconName: String? = null,
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
    override val isInTrash: Boolean = false,
    override val isInRecent: Boolean = false,
    override val isRemote: Boolean = false,
    
    // Mount Capabilities
    val canMount: Boolean = false,
    val canUnmount: Boolean = false,
    val canEject: Boolean = false,
    
    // Security
    /** SELinux security context string (e.g., "unconfined_u:object_r:user_home_t:s0"). */
    val selinuxContext: String? = null,
    
    /** Extensible bag for native-specific metadata (e.g., GIO attributes, Windows ACLs, Android Scoped Storage tags). */
    val attributes: Map<String, Any?> = emptyMap()
) : FileEntry {

    override val isEmptyDirectory: Boolean
        get() = isDirectory && childCount == 0

    /** Computed property — derived from mimeType + activationUri. True if file can be launched/executed. */
    override val isLaunchable: Boolean
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
        /** Sort by trash deletion time (newest deleted first). */
        val SortByTrashTime = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.trashTime }

        /** Sort by recency (most recently accessed first). */
        val SortByRecency = compareBy<FileInfo> { !it.isDirectory }.thenByDescending { it.recency }
    }
}
