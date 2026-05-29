@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.*
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

    fun toListingFile(
        name: String,
        parentUri: String,
        parentPath: String,
        gioInfo: org.gnome.gio.FileInfo,
        parentPathType: PathType,
        parentIsRemote: Boolean
    ): ListingFile {
        val childUri = fastChildUri(parentUri, name) ?: "$parentUri/$name"
        val childPath = "$parentPath/$name"
        val isDir = gioInfo.fileType == org.gnome.gio.FileType.DIRECTORY
        
        return ListingFile(
            name = name,
            uri = childUri,
            path = childPath,
            pathType = parentPathType,
            isDirectory = isDir,
            // Directories: skip 3 FFM calls (size, contentType, modificationDateTime)
            size = if (isDir) 0L else gioInfo.size,
            mimeType = if (isDir) "inode/directory" else gioInfo.contentType?.toString() ?: "application/octet-stream",
            modifiedTime = if (isDir) null else gioInfo.modificationDateTime?.let { kotlinx.datetime.Instant.fromEpochSeconds(it.toUnix()) },
            isHidden = name.startsWith("."),
            isInTrash = parentUri.startsWith("trash:///"),
            isInRecent = parentUri.startsWith("recent:///"),
            isRemote = parentIsRemote
        )
    }


    /**
     * Fast child URI construction. Encodes only the characters that break URI parsing (#, ?, %).
     * Returns null if the name contains characters that need encoding — caller should fall back to getChild().
     */
    fun fastChildUri(parentUri: String, name: String): String? {
        if (name.indexOfAny(CHARS_NEED_ENCODE) >= 0) return null
        return "$parentUri/$name"
    }

    /**
     * Extract local filesystem path from a file:// URI without FFM calls.
     * Returns null for non-local URIs or if decoding fails.
     */
    fun localPathFromFileUri(fileUri: String): String? {
        if (!fileUri.startsWith("file://")) return null
        return try {
            java.net.URI(fileUri).path
        } catch (_: Exception) {
            null
        }
    }

    private val CHARS_NEED_ENCODE = charArrayOf('#', '?', '%', ' ')

    /** Sentinel UUID for listing mode — avoids Uuid.random() crypto overhead per file. */
    private val LISTING_SENTINEL_UUID = Uuid.fromLongs(0, 0)

    fun toImbricFileInfo(
        uri: String,
        path: String,
        gioInfo: org.gnome.gio.FileInfo,
        backendId: String = "gio",
        extractAllAttributes: Boolean = false,
        parentUri: String? = null,
        parentPath: String? = null,
        // Pre-computed parent context — avoids per-child recalculation
        parentPathType: PathType? = null,
        parentIsRemote: Boolean? = null
    ): FileInfo {
        // Use name from parentUri if available, otherwise from gioInfo
        val name = if (parentUri != null) {
            // Extract name from URI — we already have it from getChild()
            uri.substringAfterLast('/')
        } else {
            gioInfo.name?.toString() ?: ""
        }

        // Compute child URI and path — fast path avoids getChild() FFM call
        val childUri: String
        val childPath: String
        if (parentUri != null) {
            childUri = fastChildUri(parentUri, name) ?: uri // fallback to provided uri (from getChild)
            childPath = parentPath?.let { "$it/$name" }
                ?: localPathFromFileUri(childUri)
                ?: path
        } else {
            childUri = uri
            childPath = path
        }

        // Use pre-computed parent context if available, otherwise compute per-child
        val pathType = parentPathType ?: determinePathType(if (parentUri != null) parentUri else uri)
        val isRemote = parentIsRemote ?: isRemoteUri(if (parentUri != null) parentUri else uri)

        val isDir = gioInfo.fileType == org.gnome.gio.FileType.DIRECTORY

        val nativeId = getNativeId(gioInfo)

        return FileInfo(
            nativeId = nativeId,
            name = name,
            path = childPath,
            uri = childUri,
            pathType = pathType,
            displayName = gioInfo.displayName?.toString() ?: name,
            isDirectory = isDir,
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
            owner = gioInfo.getAttributeAsString("owner::user") ?: "",
            group = gioInfo.getAttributeAsString("owner::group") ?: "",
            iconName = getIconName(gioInfo),
            thumbnailPath = gioInfo.getAttributeByteString("standard::thumbnail-path"),
            backendId = backendId,

            // Location Flags — reuse parent context
            isInTrash = (parentUri ?: uri).startsWith("trash:///"),
            isInRecent = (parentUri ?: uri).startsWith("recent:///"),
            isRemote = isRemote,

            // Mount Capabilities
            canMount = gioInfo.getAttributeBoolean("access::can-mount"),
            canUnmount = gioInfo.getAttributeBoolean("access::can-unmount"),
            canEject = gioInfo.getAttributeBoolean("access::can-eject"),

            // Virtual timestamps
            trashTime = getTrashTime(gioInfo),
            recency = getTimestamp(gioInfo, "recent::modified"),

            // Activation URI (from metadata or .desktop file)
            activationUri = gioInfo.getAttributeAsString("metadata::activation-uri"),

            // Security
            selinuxContext = gioInfo.getAttributeAsString("xattr::selinux"),

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
        extractAllAttributes: Boolean = false,
        parentUri: String? = null,
        parentPath: String? = null,
        // Pre-computed parent context — avoids per-child recalculation
        parentPathType: PathType? = null,
        parentIsRemote: Boolean? = null
    ): FileInfo {
        return toImbricFileInfo(
            uri = gfile.uri?.toString() ?: "",
            path = gfile.path?.toString() ?: gfile.uri?.toString() ?: "",
            gioInfo = gioInfo,
            backendId = backendId,
            extractAllAttributes = extractAllAttributes,
            parentUri = parentUri,
            parentPath = parentPath,
            parentPathType = parentPathType,
            parentIsRemote = parentIsRemote
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

    internal fun determinePathType(uri: String): PathType {
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
            ?: gioInfo.getAttributeAsString("standard::name")
    }

    private fun getTimestamp(gioInfo: org.gnome.gio.FileInfo, attribute: String): Instant? {
        return gioInfo.getAttributeUint64(attribute).takeIf { it > 0 }?.let { Instant.fromEpochSeconds(it) }
    }

    private fun getTrashTime(gioInfo: org.gnome.gio.FileInfo): Instant? {
        return gioInfo.getAttributeAsString("trash::deletion-date")?.let {
            try { Instant.parse(it) } catch (_: Exception) { null }
        }
    }

    internal fun isRemoteUri(uri: String): Boolean {
        return uri.contains("://") && !uri.startsWith("file://") && !uri.startsWith("trash://") && !uri.startsWith("recent://")
    }
}
