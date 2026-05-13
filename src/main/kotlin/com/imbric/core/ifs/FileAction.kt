package com.imbric.core.ifs

/**
 * Standard file operations that a backend can support or reject for a specific URI.
 */
enum class FileAction {
    READ,
    WRITE,
    DELETE,
    TRASH,
    RENAME,
    COPY_SOURCE,
    MOVE_SOURCE,
    EXECUTE,
    LIST_CHILDREN,
    WATCH
}
