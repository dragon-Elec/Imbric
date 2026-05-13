package com.imbric.core.ifs

data class PathCapabilities(
    val scheme: String,
    val isNative: Boolean,
    val isWritable: Boolean,
    val isVirtual: Boolean,
    val isLocalFile: Boolean = scheme == "file",
    val isRecent: Boolean = scheme == "recent",
    val isTrash: Boolean = scheme == "trash"
)

private val NATIVE_SCHEMES = setOf("file", "trash", "recent")
private val READONLY_SCHEMES = setOf("recent")

fun classifyPath(uri: String): PathCapabilities {
    val scheme = uri.substringBefore("://", "").ifEmpty { "file" }
    return PathCapabilities(
        scheme = scheme,
        isNative = scheme in NATIVE_SCHEMES,
        isWritable = scheme !in READONLY_SCHEMES,
        isVirtual = scheme == "recent"
    )
}
