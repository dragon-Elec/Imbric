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
        uri: String,
        path: String,
        gioInfo: org.gnome.gio.FileInfo,
        backendId: String = "gio",
        extractAllAttributes: Boolean = false
    ): FileInfo {
        val name = gioInfo.name?.toString() ?: ""
        val pathType = determinePathType(uri)
        val nativeId = getNativeId(gioInfo)
        
        return FileInfo(
            nativeId = nativeId,
            name = name,
            path = path,
            uri = uri,
            pathType = pathType,
            displayName = gioInfo.displayName?.toString() ?: name,
            isDirectory = gioInfo.fileType == org.gnome.gio.FileType.DIRECTORY,
            isSymlink = gioInfo.isSymlink,
            symlinkTarget = if (gioInfo.isSymlink) gioInfo.symlinkTarget?.toString() else null,
            size = gioInfo.size,
            mimeType = gioInfo.contentType?.toString() ?: "application/octet-stream",
            modifiedTime = gioInfo.modificationDateTime?.let { Instant.fromEpochSeconds(it.toUnix()) },
            accessedTime = getTimestamp(gioInfo, "time::access"),
            createdTime = getTimestamp(gioInfo, "time::created"),
            isHidden = gioInfo.isHidden,
            isReadable = gioInfo.getAttributeBoolean("access::can-read"),
            isWritable = gioInfo.getAttributeBoolean("access::can-write"),
            isExecutable = gioInfo.getAttributeBoolean("access::can-execute"),
            permissions = gioInfo.getAttributeUint32("unix::mode").takeIf { it > 0 }?.toString(8) ?: "",
            owner = gioInfo.getAttributeString("owner::user") ?: "",
            group = gioInfo.getAttributeString("owner::group") ?: "",
            iconName = getIconName(gioInfo),
            thumbnailPath = gioInfo.getAttributeString("standard::thumbnail-path"),
            backendId = backendId,
            
            // Location Flags
            isInTrash = uri.startsWith("trash:///"),
            isInRecent = uri.startsWith("recent:///"),
            isRemote = isRemoteUri(uri),
            
            // Mount Capabilities
            canMount = gioInfo.getAttributeBoolean("access::can-mount"),
            canUnmount = gioInfo.getAttributeBoolean("access::can-unmount"),
            canEject = gioInfo.getAttributeBoolean("access::can-eject"),
            
            // Virtual timestamps
            trashTime = getTrashTime(gioInfo),
            recency = getTimestamp(gioInfo, "recent::modified"),
            
            // Activation URI (from metadata or .desktop file)
            activationUri = gioInfo.getAttributeString("metadata::activation-uri"),
            
            // Security
            selinuxContext = gioInfo.getAttributeString("xattr::selinux"),
            
            attributes = if (extractAllAttributes) {
                extractAttributes(gioInfo)
            } else {
                buildMap {
                    gioInfo.getAttributeStringv("metadata::emblems")?.let { put("metadata::emblems", it.toList()) }
                }
            }
        )
    }

    fun toImbricFileInfo(
        gfile: org.gnome.gio.File, 
        gioInfo: org.gnome.gio.FileInfo,
        backendId: String = "gio",
        extractAllAttributes: Boolean = false
    ): FileInfo {
        return toImbricFileInfo(
            uri = gfile.uri?.toString() ?: "",
            path = gfile.path?.toString() ?: gfile.uri?.toString() ?: "",
            gioInfo = gioInfo,
            backendId = backendId,
            extractAllAttributes = extractAllAttributes
        )
    }

    private fun extractAttributes(gioInfo: org.gnome.gio.FileInfo): Map<String, Any?> {
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
                    org.gnome.gio.FileAttributeType.STRINGV -> gioInfo.getAttributeStringv(attr)?.toList()
                    else -> null
                }
            }
        }
        return attributeMap
    }

    private fun determinePathType(uri: String): PathType {
        return when {
            uri.startsWith("trash://") || uri.startsWith("recent://") -> PathType.VIRTUAL
            else -> PathType.PHYSICAL
        }
    }

    private fun getIconName(gioInfo: org.gnome.gio.FileInfo): String? {
        val icon = gioInfo.icon
        return if (icon is org.gnome.gio.ThemedIcon) icon.names?.firstOrNull() else null
    }

    private fun getNativeId(gioInfo: org.gnome.gio.FileInfo): String? {
        return gioInfo.getAttributeUint64("unix::inode").takeIf { it > 0 }?.toString()
            ?: gioInfo.getAttributeString("standard::name")
    }

    private fun getTimestamp(gioInfo: org.gnome.gio.FileInfo, attribute: String): Instant? {
        return gioInfo.getAttributeUint64(attribute).takeIf { it > 0 }?.let { Instant.fromEpochSeconds(it) }
    }

    private fun getTrashTime(gioInfo: org.gnome.gio.FileInfo): Instant? {
        return gioInfo.getAttributeString("trash::deletion-date")?.let {
            try { Instant.parse(it) } catch (_: Exception) { null }
        }
    }

    private fun isRemoteUri(uri: String): Boolean {
        return uri.contains("://") && !uri.startsWith("file://") && !uri.startsWith("trash://") && !uri.startsWith("recent://")
    }
}
