package com.imbric.core.models

import kotlin.time.Instant

data class ListingFile(
    override val name: String,
    override val uri: String,
    override val path: String,
    override val isDirectory: Boolean,
    override val pathType: PathType,
    override val size: Long = 0L,
    override val mimeType: String = "application/octet-stream",
    override val modifiedTime: Instant? = null,
    override val isHidden: Boolean = false,
    override val iconName: String? = null,
    override val isInTrash: Boolean = false,
    override val isInRecent: Boolean = false,
    override val isRemote: Boolean = false
) : FileEntry
