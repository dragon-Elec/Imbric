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

    private fun isRootUri(): Boolean = uriString.matches(Regex("^\\w+:/{2,3}$"))

    val name: String
        get() {
            if (isRootUri()) return "/"
            val cleanUri = uriString.trimEnd('/')
            if (cleanUri.isEmpty()) return "/"
            return cleanUri.substringAfterLast("/")
        }

    val parent: IfsUri
        get() {
            if (isRootUri()) return IfsUri("$scheme:///")
            val cleanUri = uriString.trimEnd('/')
            val schemeEnd = cleanUri.indexOf("://")
            val lastSlash = cleanUri.lastIndexOf('/')
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
        if (isRootUri()) return IfsUri("$scheme:///${child.trimStart('/')}")
        val base = uriString.trimEnd('/')
        val safeChild = child.trimStart('/')
        return IfsUri("$base/$safeChild")
    }

    fun renameTarget(newName: String): IfsUri = parent.join(newName)

    override fun toString(): String = uriString
}

val String.uriName: String get() = IfsUri(this).name
val String.uriParent: String get() = IfsUri(this).parent.uriString
fun String.uriJoin(child: String): String = IfsUri(this).join(child).uriString
