package com.imbric.core.ifs.provider

/**
 * Describes the kind of directory a [DirState] represents.
 * Derived from the URI scheme — no backend involvement needed.
 *
 * This is the Kotlin equivalent of Nautilus's directory subclassing
 * (NautilusSearchDirectory, NautilusVfsDirectory, etc.),
 * but using a sealed enum instead of class inheritance.
 */
enum class DirectoryType {
    /** Normal filesystem directory (file:// or bare path). */
    REGULAR,
    
    /** Trash folder (trash://). Shows deleted files with restore capability. */
    TRASH,
    
    /** Recent files (recent://). Shows recently accessed files. */
    RECENT,
    
    /** Starred/bookmarked files. Aggregated from StarredManager, not a real filesystem location. */
    STARRED,
    
    /** Search results. Content comes from IOBackend.search(), not IOBackend.list(). */
    SEARCH,
    
    /** Network/SMB/SFTP mount. May have different latency and capability profiles. */
    NETWORK,
    
    /** Other virtual directories (bookmarks sidebar, custom aggregations, etc.). */
    OTHER;

    companion object {
        /**
         * Derives the [DirectoryType] from a URI scheme.
         * This is a pure function — no backend calls needed.
         */
        fun fromUri(uri: String): DirectoryType {
            val scheme = uri.substringBefore("://", "").lowercase()
            return when {
                scheme == "trash" -> TRASH
                scheme == "recent" -> RECENT
                scheme == "starred" -> STARRED
                scheme == "search" -> SEARCH
                scheme == "smb" || scheme == "sftp" || scheme == "ftp" || scheme == "mtp" -> NETWORK
                scheme.isEmpty() || scheme == "file" -> REGULAR
                else -> OTHER
            }
        }
    }
}
