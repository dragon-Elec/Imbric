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
        val name = gioInfo.name?.toString() ?: ""
        val uri = gfile.uri?.toString() ?: ""
        
        val icon = gioInfo.icon
        val iconName = if (icon is org.gnome.gio.ThemedIcon) icon.names?.firstOrNull() else null

        // Native GIO attributes (Secret Bag)
        val attributeMap = mutableMapOf<String, Any?>()
        gioInfo.listAttributes(null)?.forEach { attr ->
            if (attr != null) {
                val type = gioInfo.getAttributeType(attr)
                attributeMap[attr] = when (type) {
                    org.gnome.gio.FileAttributeType.STRING -> gioInfo.getAttributeString(attr)
                    org.gnome.gio.FileAttributeType.BYTE_STRING -> gioInfo.getAttributeByteString(attr)
                    org.gnome.gio.FileAttributeType.BOOLEAN -> gioInfo.getAttributeBoolean(attr)
                    org.gnome.gio.FileAttributeType.UINT32 -> gioInfo.getAttributeUint32(attr)
                    org.gnome.gio.FileAttributeType.INT32 -> gioInfo.getAttributeInt32(attr)
                    org.gnome.gio.FileAttributeType.UINT64 -> gioInfo.getAttributeUint64(attr)
                    org.gnome.gio.FileAttributeType.INT64 -> gioInfo.getAttributeInt64(attr)
                    org.gnome.gio.FileAttributeType.OBJECT -> gioInfo.getAttributeObject(attr)
                    org.gnome.gio.FileAttributeType.STRINGV -> gioInfo.getAttributeStringv(attr)
                    else -> null
                }
            }
        }

        val pathType = when {
            uri.startsWith("trash://") || uri.startsWith("recent://") -> PathType.VIRTUAL
            else -> PathType.PHYSICAL
        }

        // Native identifier for stable tracking across renames
        val nativeId = gioInfo.getAttributeUint64("unix::inode").takeIf { it > 0 }?.toString()
            ?: gioInfo.getAttributeString("standard::name")

        return FileInfo(
            nativeId = nativeId,
            name = name,
            path = gfile.path?.toString() ?: uri,
            uri = uri,
            pathType = pathType,
            displayName = gioInfo.displayName?.toString() ?: name,
            isDirectory = gioInfo.fileType == org.gnome.gio.FileType.DIRECTORY,
            isSymlink = gioInfo.isSymlink,
            symlinkTarget = if (gioInfo.isSymlink) gioInfo.symlinkTarget?.toString() else null,
            size = gioInfo.size,
            mimeType = gioInfo.contentType?.toString() ?: "application/octet-stream",
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
            
            // Location Flags
            isInTrash = uri.startsWith("trash:///"),
            isInRecent = uri.startsWith("recent:///"),
            isRemote = uri.contains("://") && !uri.startsWith("file://") && !uri.startsWith("trash://") && !uri.startsWith("recent://"),
            
            // Mount Capabilities
            canMount = gioInfo.getAttributeBoolean("access::can-mount"),
            canUnmount = gioInfo.getAttributeBoolean("access::can-unmount"),
            canEject = gioInfo.getAttributeBoolean("access::can-eject"),
            
            // Virtual timestamps
            trashTime = gioInfo.getAttributeString("trash::deletion-date")?.let {
                try { Instant.parse(it) } catch (_: Exception) { null }
            },
            recency = gioInfo.getAttributeUint64("recent::modified").takeIf { it > 0 }
                ?.let { Instant.fromEpochSeconds(it) },
            
            // Activation URI (from metadata or .desktop file)
            activationUri = gioInfo.getAttributeString("metadata::activation-uri"),
            
            // Security
            selinuxContext = gioInfo.getAttributeString("xattr::selinux"),
            
            attributes = attributeMap
        )
    }
}
