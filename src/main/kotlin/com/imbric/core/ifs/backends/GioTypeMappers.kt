@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.FileInfo
import com.imbric.core.models.PathType
import kotlinx.datetime.Instant
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Isolated mapper to convert GIO native types to Imbric models.
 * This file owns the name collisions (org.gnome.gio.FileInfo vs com.imbric.core.models.FileInfo)
 * so that backends stay clean.
 */
object GioTypeMappers {

    fun toImbricFileInfo(
        gfile: org.gnome.gio.File, 
        gioInfo: org.gnome.gio.FileInfo,
        backendId: String = "gio"
    ): FileInfo {
        val fileType = gioInfo.fileType
        val name = gioInfo.name ?: ""
        val displayName = gioInfo.displayName ?: name
        val uri = gfile.uri
        
        val pathType = when {
            uri.startsWith("trash://") || uri.startsWith("recent://") -> PathType.VIRTUAL
            else -> PathType.PHYSICAL
        }

        val nativeId = gioInfo.getAttributeUint64("unix::inode").takeIf { it > 0 }?.toString() 
            ?: gioInfo.getAttributeString("standard::name")

        val icon = gioInfo.icon
        val iconName = if (icon is org.gnome.gio.ThemedIcon) {
            icon.names?.firstOrNull()
        } else {
            null
        }

        val attributeMap = mutableMapOf<String, Any?>()
        gioInfo.listAttributes(null)?.forEach { attr ->
            if (attr != null) {
                attributeMap[attr] = gioInfo.getAttributeAsString(attr)
            }
        }

        return FileInfo(
            id = Uuid.random(),
            nativeId = nativeId,
            path = gfile.path ?: gfile.uri,
            uri = gfile.uri,
            pathType = pathType,
            name = name,
            displayName = displayName,
            isDirectory = fileType == org.gnome.gio.FileType.DIRECTORY,
            isSymlink = gioInfo.isSymlink,
            symlinkTarget = if (gioInfo.isSymlink) gioInfo.symlinkTarget else null,
            size = gioInfo.size,
            mimeType = gioInfo.contentType ?: "application/octet-stream",
            modifiedTime = gioInfo.modificationDateTime?.let { Instant.fromEpochSeconds(it.toUnix()) },
            accessedTime = gioInfo.getAttributeUint64("time::access").takeIf { it > 0 }?.let { Instant.fromEpochSeconds(it) },
            createdTime = gioInfo.getAttributeUint64("time::created").takeIf { it > 0 }?.let { Instant.fromEpochSeconds(it) },
            isHidden = gioInfo.isHidden,
            isReadable = gioInfo.getAttributeBoolean("access::can-read"),
            isWritable = gioInfo.getAttributeBoolean("access::can-write"),
            isExecutable = gioInfo.getAttributeBoolean("access::can-execute"),
            permissions = gioInfo.getAttributeUint32("unix::mode").takeIf { it > 0 }?.toString(8) ?: "",
            owner = gioInfo.getAttributeString("owner::user") ?: "",
            group = gioInfo.getAttributeString("owner::group") ?: "",
            iconName = iconName,
            thumbnailPath = gioInfo.getAttributeString("standard::thumbnail-path"),
            backendId = backendId,
            attributes = attributeMap
        )
    }
}
