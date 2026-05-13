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
    /** Extensible bag for native-specific metadata (e.g., GIO attributes, Windows ACLs, Android Scoped Storage tags). */
    val attributes: Map<String, Any?> = emptyMap()
) {
    val extension: String
        get() = name.substringAfterLast('.', "")

    val isEmptyDirectory: Boolean
        get() = isDirectory && childCount == 0
}
