package com.imbric.core.logic

/**
 * Characters forbidden in filenames on FAT/exFAT filesystems.
 * These are also problematic on NTFS and some network shares.
 *
 * Ported from nautilus-file-operations.c FAT_FORBIDDEN_CHARACTERS.
 */
const val FAT_FORBIDDEN_CHARACTERS = ":|<>*?\\\"/"

/**
 * Checks if a filename component is valid.
 * A valid component is non-blank, not "." or "..", and contains no forbidden characters.
 *
 * This validates a single path component (e.g., "budget.xlsx"), NOT a full URI or path.
 */
fun isValidComponentName(name: String): Boolean {
    if (name.isBlank()) return false
    if (name == "." || name == "..") return false
    return name.none { it in FAT_FORBIDDEN_CHARACTERS }
}

/**
 * Returns the set of forbidden characters found in the name, or empty set if valid.
 */
fun findForbiddenChars(name: String): Set<Char> {
    return name.filter { it in FAT_FORBIDDEN_CHARACTERS }.toSet()
}
