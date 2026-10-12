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
            // Directories: skip 3 attribute reads (size, contentType, mtime).
            // Directories also keep a null mtime deliberately: GIO watch
            // events already cover directories (a child add fires CREATED
            // on the parent), and a real dir mtime would churn on every
            // child change — re-firing DirState's dedup fingerprint per
            // child add for no new information.
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

        val isDir = (effectiveType ?: gioInfo.fileType) == org.gnome.gio.FileType.DIRECTORY

        val nativeId = getNativeId(gioInfo)

        // --- Permission flags (fast path derives from unix::mode owner bits) ---
        // mode and owner are fetched once here and reused below (no extra FFM calls).
        val unixMode = gioInfo.getAttributeUint32("unix::mode")
        val ownerName = gioInfo.getAttributeAsString("owner::user")
        // Owner-match: derive R/X from the mode's OWNER bits only when the file is
        // owned by us AND mode > 0 (0 = attribute absent, e.g. non-unix fs, not "no
        // perms"). Group/ACL membership is unknown here, so non-owned files keep GIO's
        // access::can-* queries. Write always reads access::can-write: ACLs, group
        // grants and read-only mounts override owner bits, and it gates
        // XferArbiter.canOverwrite + the readonly emblem, where a lie is user-visible.
        val deriveFromOwnerBits = unixMode > 0 && ownerName != null && ownerName == CURRENT_USER_NAME
        val isReadable = if (deriveFromOwnerBits) (unixMode and 0x100) != 0 else gioInfo.getAttributeBoolean("access::can-read")
        val isWritable = gioInfo.getAttributeBoolean("access::can-write")
        val isExecutable = if (deriveFromOwnerBits) (unixMode and 0x40) != 0 else gioInfo.getAttributeBoolean("access::can-execute")

        return FileInfo(
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

            isInTrash = (parentUri ?: uri).startsWith("trash:///"),
            isInRecent = (parentUri ?: uri).startsWith("recent:///"),
            isRemote = isRemote,

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

    /**
     * Reads a GIO time attribute as an [Instant] at millisecond precision.
     *
     * Every `time::*` attribute has a `*-nsec` companion (e.g. `time::modified`
     * and `time::modified-nsec`) carrying the nanosecond remainder; pairing
     * them here — the single choke point every mtime/atime/ctime read goes
     * through — makes a same-second, same-size rewrite observable, because
     * DirState's dedup pass and the conflict fingerprint compare modifiedTime
     * directly. Whole-second truncation would swallow such an edit.
     *
     * The paired value is truncated to milliseconds, not carried at full
     * nanosecond precision: [ListingDirectory] stores epoch millis and reads
     * rows back through [Instant.fromEpochMilliseconds], and the dedup pass
     * compares [Instant] equality. [Instant] keeps nanosecondsOfSecond, so a
     * sub-millisecond value would never equal its own cached read-back —
     * every refresh would treat every unchanged row as changed and the dedup
     * pass could never reuse the cached row. Millis is the finest precision
     * the listing layer can round-trip.
     *
     * [org.gnome.gio.FileInfo.hasAttribute] is the presence check: a queried
     * attribute the filesystem left unset is absent (→ null), while a
     * present-but-zero value is a real 1970 epoch-0 timestamp. The old
     * `takeIf { it > 0 }` gate conflated the two and mapped epoch-0 to null.
     * Namespaces without an nsec companion (e.g. `recent::modified`) simply
     * have no `*-nsec` attribute, so they keep whole-second precision.
     */
    private fun getTimestamp(gioInfo: org.gnome.gio.FileInfo, attribute: String): Instant? {
        if (!gioInfo.hasAttribute(attribute)) return null
        val seconds = gioInfo.getAttributeUint64(attribute)
        val nsecAttribute = "$attribute-nsec"
        val nanos = if (gioInfo.hasAttribute(nsecAttribute)) {
            gioInfo.getAttributeUint32(nsecAttribute).toLong()
        } else 0L
        return Instant.fromEpochMilliseconds(seconds * 1000 + nanos / 1_000_000)
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
