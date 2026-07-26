package com.imbric.core.ifs

data class PathCapabilities(
    val scheme: String,
    /** Handled by the core VFS (not an external protocol). */
    val isNative: Boolean,
    /** Supports write operations (not a read-only scheme). */
    val isWritable: Boolean,
    /** Listing is synthesized (not a real filesystem directory). */
    val isVirtual: Boolean,
    /** Local file:// or bare path. */
    val isLocalFile: Boolean = scheme == "file",
    /** recent:// scheme. */
    val isRecent: Boolean = scheme == "recent",
    /** trash:// scheme. */
    val isTrash: Boolean = scheme == "trash"
)

/** Schemes handled natively by the VFS layer (not external protocol handlers). */
private val NATIVE_SCHEMES = setOf("file", "trash", "recent", "starred", "search")
/** Schemes that are read-only by nature. */
private val READONLY_SCHEMES = setOf("recent", "starred", "search")
/** Schemes whose listing is synthesized, not a real filesystem directory. */
private val VIRTUAL_SCHEMES = setOf("trash", "recent", "starred", "search")

fun classifyPath(uri: String): PathCapabilities {
    val scheme = uri.substringBefore("://", "").ifEmpty { "file" }
    return PathCapabilities(
        scheme = scheme,
        isNative = scheme in NATIVE_SCHEMES,
        isWritable = scheme !in READONLY_SCHEMES,
        isVirtual = scheme in VIRTUAL_SCHEMES
    )
}
