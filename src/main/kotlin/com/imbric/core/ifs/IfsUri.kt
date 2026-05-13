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

    val name: String
        get() {
            val cleanUri = uriString.trimEnd('/')
            if (cleanUri.endsWith("://")) return "/"
            if (cleanUri.isEmpty()) return "/"
            return cleanUri.substringAfterLast("/")
        }

    val parent: IfsUri
        get() {
            val cleanUri = uriString.trimEnd('/')
            val schemeSplit = cleanUri.indexOf("://")
            if (schemeSplit != -1 && cleanUri.length <= schemeSplit + 3) return this
            val lastSlash = cleanUri.lastIndexOf('/')
            if (lastSlash <= schemeSplit + 2) return IfsUri("$scheme:///")
            return IfsUri(cleanUri.substring(0, lastSlash).ifEmpty { "/" })
        }

    val extension: String
        get() = name.substringAfterLast('.', "")

    val nameWithoutExtension: String
        get() {
            val n = name
            val dotIdx = n.lastIndexOf('.')
            return if (dotIdx > 0) n.substring(0, dotIdx) else n
        }

    fun join(child: String): IfsUri {
        val base = uriString.trimEnd('/')
        val safeChild = child.trimStart('/')
        return if (base.endsWith("://")) IfsUri("$base$safeChild") else IfsUri("$base/$safeChild")
    }

    fun renameTarget(newName: String): IfsUri = parent.join(newName)

    override fun toString(): String = uriString
}

val String.uriName: String get() = IfsUri(this).name
val String.uriParent: String get() = IfsUri(this).parent.uriString
fun String.uriJoin(child: String): String = IfsUri(this).join(child).uriString
