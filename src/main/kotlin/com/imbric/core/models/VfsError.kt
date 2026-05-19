package com.imbric.core.models

/**
 * Typed error hierarchy for VFS operations.
 * Core produces these; app layer maps them to user-facing messages (i18n).
 *
 * Each variant carries the URI context so the app can produce messages like
 * "Could not rename 'budget.xlsx' because a file with that name already exists."
 *
 * Ported from nautilus-error-reporting.h / GIO's IOErrorEnum.
 */
sealed class VfsError(
    override val message: String,
    override val cause: Throwable? = null
) : Exception(message, cause) {

    /** File or directory already exists at the destination. */
    class AlreadyExists(
        val uri: String,
        message: String = "File already exists: $uri"
    ) : VfsError(message)

    /** File or directory not found. */
    class NotFound(
        val uri: String,
        message: String = "File not found: $uri"
    ) : VfsError(message)

    /** Operation would cause infinite recursion (e.g., moving a folder into itself). */
    class WouldRecurse(
        val uri: String,
        message: String = "Operation would recurse: $uri"
    ) : VfsError(message)

    /** Permission denied. */
    class PermissionDenied(
        val uri: String,
        message: String = "Permission denied: $uri"
    ) : VfsError(message)

    /** Filename contains forbidden characters (e.g., FAT filesystem). */
    class InvalidName(
        val name: String,
        val forbiddenChars: Set<Char>,
        message: String = "Invalid filename: '$name' contains forbidden characters: ${forbiddenChars.joinToString("")}"
    ) : VfsError(message)

    /** Disk is full or quota exceeded. */
    class NoSpace(
        val uri: String,
        message: String = "No space left on device: $uri"
    ) : VfsError(message)

    /** Target is read-only. */
    class ReadOnly(
        val uri: String,
        message: String = "Read-only file system: $uri"
    ) : VfsError(message)

    /** Operation was cancelled (user action or timeout). */
    class Cancelled(
        val uri: String = "",
        message: String = "Operation cancelled"
    ) : VfsError(message)

    /** Filesystem or backend does not support this operation. */
    class NotSupported(
        val uri: String,
        message: String = "Operation not supported: $uri"
    ) : VfsError(message)

    /** Expected a file but found a directory (or vice versa). */
    class IsDirectory(
        val uri: String,
        message: String = "Is a directory: $uri"
    ) : VfsError(message)

    /** Expected a directory but found a file. */
    class NotDirectory(
        val uri: String,
        message: String = "Not a directory: $uri"
    ) : VfsError(message)

    /** File is locked or busy. */
    class Busy(
        val uri: String,
        message: String = "File is busy or locked: $uri"
    ) : VfsError(message)

    /** Generic I/O error — catch-all for unmapped GIO errors. */
    class IoError(
        val uri: String = "",
        message: String = "I/O error",
        cause: Throwable? = null
    ) : VfsError(message, cause)

    override fun toString(): String = "${this::class.simpleName}: $message"
}
