package com.imbric.core.ifs

@JvmInline
value class IfsUri(val uriString: String) {

    val scheme: String
        get() {
            val idx = uriString.indexOf("://")
            return if (idx != -1) uriString.substring(0, idx) else "file"
        }

    val isNative: Boolean
        get() = scheme == "file" || scheme == "trash" || scheme == "recent"

    fun isRootUri(): Boolean {
        // Scheme-based root: file:///, smb:///, etc.
        if (ROOT_URI_REGEX.matches(uriString)) return true
        // Plain path root: "/" or "" (empty after trim)
        val trimmed = uriString.trimEnd('/')
        return trimmed.isEmpty() || trimmed == "/"
    }

    val name: String
        get() {
            if (isRootUri()) return "/"
            val cleanUri = uriString.trimEnd('/')
            if (cleanUri.isEmpty()) return "/"
            return cleanUri.substringAfterLast("/")
        }

    val parent: IfsUri
        get() {
            if (isRootUri()) {
                // Plain path root "/" stays "/"; scheme roots become "$scheme:///"
                return if (uriString.contains("://")) IfsUri("$scheme:///") else IfsUri("/")
            }
            val cleanUri = uriString.trimEnd('/')
            val schemeEnd = cleanUri.indexOf("://")
            val lastSlash = cleanUri.lastIndexOf('/')
            // Plain path (no scheme) — e.g. /path/to/file → /path/to
            if (schemeEnd == -1) {
                return if (lastSlash <= 0) IfsUri("/") else IfsUri(cleanUri.substring(0, lastSlash))
            }
            // Scheme-based URI — e.g. file:///path → file:///
            if (lastSlash <= schemeEnd + 3) return IfsUri("$scheme:///")
            return IfsUri(cleanUri.substring(0, lastSlash).ifEmpty { "/" })
        }

    val extension: String
        get() = name.substringAfterLast('.', "")

    val nameWithoutExtension: String
        get() {
            val n = name
            val dotIdx = n.lastIndexOf('.')
            return when {
                dotIdx > 0 -> n.substring(0, dotIdx)
                dotIdx == 0 -> ""  // Hidden file like .hidden — no name part
                else -> n  // No extension at all
            }
        }

    fun join(child: String): IfsUri {
        if (isRootUri()) {
            // Plain path root "/" joins as "/child"; scheme roots join as "$scheme:///child"
            return if (uriString.contains("://")) {
                IfsUri("$scheme:///${child.trimStart('/')}")
            } else {
                IfsUri("/${child.trimStart('/')}")
            }
        }
        val base = uriString.trimEnd('/')
        val safeChild = child.trimStart('/')
        return IfsUri("$base/$safeChild")
    }

    fun renameTarget(newName: String): IfsUri = parent.join(newName)

    override fun toString(): String = uriString

    private companion object {
        // Compiled once at class init — avoids recompiling on every isRootUri() call.
        // Pattern matches scheme:// or scheme:/// (root URIs).
        val ROOT_URI_REGEX = Regex("^\\w+:/{2,3}$")
    }
}

val String.uriName: String get() = IfsUri(this).name
val String.uriParent: String get() = IfsUri(this).parent.uriString
fun String.uriJoin(child: String): String = IfsUri(this).join(child).uriString
