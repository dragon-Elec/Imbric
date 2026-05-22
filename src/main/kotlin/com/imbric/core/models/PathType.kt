package com.imbric.core.models

/**
 * Categorizes the nature of a path.
 */
enum class PathType {
    /** A real file on a physical or network filesystem (e.g., /home/user, smb://server/file) */
    PHYSICAL,
    /** A virtual aggregation (e.g., trash:///, recent:///, search://) */
    VIRTUAL,
    /** A generated or synthetic entry (e.g., system://info, settings://core) */
    SYNTHETIC
}
