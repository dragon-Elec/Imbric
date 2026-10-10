@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends.gio.support

import com.imbric.core.models.*
import com.imbric.core.models.PathType
import kotlin.time.Instant
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Isolated mapper to convert GIO native types to Imbric models.
 * This file owns the name collisions (org.gnome.gio.FileInfo vs com.imbric.core.models.FileInfo)
 * so that backends stay clean.
 */
object GioTypeMappers {
    private val mimeCache = java.util.concurrent.ConcurrentHashMap<String, String>()

    /** Current OS user name, cached once — owner-match rule for the permission fast path. */
    private val CURRENT_USER_NAME: String? = System.getProperty("user.name")

    private fun internMime(mime: String?): String {
        if (mime == null) return "application/octet-stream"
        return mimeCache.getOrPut(mime) { mime }
    }

    fun toListingFile(
        name: String,
        parentUri: String,
        parentPath: String,
        gioInfo: org.gnome.gio.FileInfo,
        parentPathType: PathType,
        parentIsRemote: Boolean,
        effectiveType: org.gnome.gio.FileType? = null
    ): ListingFile {
        val childUri = fastChildUri(parentUri, name)
        val childPath = "$parentPath/$name"
        // NOFOLLOW listings report SYMBOLIC_LINK for links, so a symlink's own
        // fileType never says what it points at. Callers that can afford one
        // follow-query pass the target's type here; a symlink whose target is a
        // directory then gets full directory semantics (folder icon, navigable,
        // size 0, directory mime, null mtime — Nautilus parity). null (non-links,
        // broken links, ELOOP) keeps the symlink's own type.
        val isDir = (effectiveType ?: gioInfo.fileType) == org.gnome.gio.FileType.DIRECTORY
        // Read once: standard::is-symlink is part of the shared listing attribute set
        // (FileEntry.listingAttributesFor), so this is a field read, not an extra FFI call.
        val isLink = gioInfo.isSymlink
        
        return ListingFile(
            name = name,
            uri = childUri,
            path = childPath,
            pathType = parentPathType,
            isDirectory = isDir,
            // Directories: skip 3 attribute reads (size, contentType, mtime)
            size = if (isDir) 0L else gioInfo.size,
            mimeType = if (isDir) "inode/directory" else internMime(gioInfo.contentType),
            modifiedTime = if (isDir) null else getTimestamp(gioInfo, "time::modified"),
            isHidden = name.startsWith("."),
            isInTrash = parentUri.startsWith("trash:///"),
            isInRecent = parentUri.startsWith("recent:///"),
            isRemote = parentIsRemote,
            isSymlink = isLink
        )
    }


    /**
     * Fast child URI construction. Percent-encodes the name per RFC 3986.
     * Unreserved chars (A-Z a-z 0-9 - _ . ~) pass through; everything else is percent-encoded.
     * Always returns a valid URI — never falls back.
     */
    fun fastChildUri(parentUri: String, name: String): String {
        val encodedName = name.percentEncodeForUri()
        return "$parentUri/$encodedName"
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

    /** RFC 3986 percent-encoding: encodes to UTF-8 bytes first, then percent-encodes each byte. */
    private fun String.percentEncodeForUri(): String {
        // Fast path: a purely unreserved ASCII name (the common case) needs no encoding.
        var i = 0
        while (i < length) {
            val c = this[i]
            if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
                || c == '-' || c == '_' || c == '.' || c == '~')) break
            i++
        }
        if (i == length) return this
        return buildString(length * 3) {
            val bytes = this@percentEncodeForUri.encodeToByteArray() // UTF-8
            for (b in bytes) {
                val unsigned = b.toInt() and 0xFF
                when {
                    unsigned in 'A'.code..'Z'.code || unsigned in 'a'.code..'z'.code
                        || unsigned in '0'.code..'9'.code
                        || unsigned == '-'.code || unsigned == '_'.code
                        || unsigned == '.'.code || unsigned == '~'.code -> append(unsigned.toChar())
                    else -> {
                        append('%')
                        append(Integer.toHexString(unsigned).uppercase().padStart(2, '0'))
                    }
                }
            }
        }
    }

    /** Shared sentinel UUID — avoids Uuid.random() crypto overhead per row (listing + metadata). */
    private val SENTINEL_UUID = Uuid.fromLongs(0, 0)

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
        parentIsRemote: Boolean? = null,
        effectiveType: org.gnome.gio.FileType? = null
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
            childUri = fastChildUri(parentUri, name)
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

        // effectiveType overrides the NOFOLLOW-reported type for symlinks
        // whose target the caller resolved with a follow-query (search walk);
        // null keeps gioInfo.fileType (getMetadata already queries with NONE,
        // which follows links, so its type is the target's own).
        val isDir = (effectiveType ?: gioInfo.fileType) == org.gnome.gio.FileType.DIRECTORY

        val nativeId = getNativeId(gioInfo)

        // --- Permission flags (fast path derives from unix::mode owner bits) ---
        // mode and owner are fetched once here and reused below (no extra FFM calls).
        val unixMode = gioInfo.getAttributeUint32("unix::mode")
        val ownerName = gioInfo.getAttributeAsString("owner::user")
        // Owner-match rule: derive the booleans from the mode's OWNER bits only when
        // the file is owned by the current user AND mode > 0. mode == 0 means the
        // attribute is absent (e.g. non-unix filesystems), where deriving would wrongly
        // yield all-false. The fallback exists because effective access depends on
        // ownership AND group membership (and ACLs); we only have the owner name, not
        // the current user's group list, so files owned by others must keep GIO's
        // access::can-* queries, which apply full ACL/group semantics.
        val deriveFromOwnerBits = unixMode > 0 && ownerName != null && ownerName == CURRENT_USER_NAME
        // Owner bits: read = 0o400 (0x100), write = 0o200 (0x80), execute = 0o100 (0x40).
        // For the owning user, effective access equals the owner permission bits.
        val isReadable = if (deriveFromOwnerBits) (unixMode and 0x100) != 0 else gioInfo.getAttributeBoolean("access::can-read")
        val isWritable = if (deriveFromOwnerBits) (unixMode and 0x80) != 0 else gioInfo.getAttributeBoolean("access::can-write")
        val isExecutable = if (deriveFromOwnerBits) (unixMode and 0x40) != 0 else gioInfo.getAttributeBoolean("access::can-execute")

        return FileInfo(
            // Shared sentinel id — FileInfo.id is not a unique key (FileEntry does not
            // declare it, no code reads it, and the listing path already shares one
            // sentinel across all rows). Avoids a contended Uuid.random() crypto draw
            // per metadata row.
            id = SENTINEL_UUID,
            nativeId = nativeId,
            name = name,
            path = childPath,
            uri = childUri,
            pathType = pathType,
            displayName = gioInfo.displayName ?: name,
            isDirectory = isDir,
            isSymlink = gioInfo.isSymlink,
            symlinkTarget = if (gioInfo.isSymlink) gioInfo.symlinkTarget?.toString() else null,
            size = gioInfo.size,
            mimeType = internMime(gioInfo.contentType),
            modifiedTime = getTimestamp(gioInfo, "time::modified"),
            accessedTime = getTimestamp(gioInfo, "time::access"),
            createdTime = getTimestamp(gioInfo, "time::created"),
            isHidden = gioInfo.isHidden,
            isReadable = isReadable,
            isWritable = isWritable,
            isExecutable = isExecutable,
            permissions = unixMode.takeIf { it > 0 }?.toString(8) ?: "",
            owner = ownerName ?: "",
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
        parentIsRemote: Boolean? = null,
        effectiveType: org.gnome.gio.FileType? = null
    ): FileInfo {
        return toImbricFileInfo(
            uri = gfile.uri ?: "",
            path = gfile.path?.toString() ?: gfile.uri ?: "",
            gioInfo = gioInfo,
            backendId = backendId,
            extractAllAttributes = extractAllAttributes,
            parentUri = parentUri,
            parentPath = parentPath,
            parentPathType = parentPathType,
            parentIsRemote = parentIsRemote,
            effectiveType = effectiveType
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
