package com.imbric.core.ifs

enum class Locality {
    LOCAL,
    NETWORK,
    VIRTUAL
}

data class BackendCapabilities(
    val locality: Locality = Locality.LOCAL,
    val supportsBatch: Boolean = true,
    val supportsSearch: Boolean = false,
    val supportsTrash: Boolean = true,
    val supportsSymlinks: Boolean = true,
    val reliableMtime: Boolean = true,
    val reliableSize: Boolean = true,
    val caseSensitive: Boolean = true
)
