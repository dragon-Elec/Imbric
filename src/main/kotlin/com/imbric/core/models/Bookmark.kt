package com.imbric.core.models

import kotlinx.serialization.Serializable

/**
 * A user-saved location (bookmark).
 * Core data contract — no GIO or platform dependencies.
 *
 * Ported from nautilus-bookmark.h / NautilusBookmark.
 *
 * @param name Display name derived from the URI (e.g., "Documents")
 * @param uri The bookmarked location URI (e.g., "file:///home/user/Documents")
 * @param label Optional user-customizable label (overrides [name] in UI)
 * @param icon Optional icon name for the themed icon (e.g., "folder-documents")
 * @param symbolicIcon Optional symbolic icon name (e.g., "folder-documents-symbolic")
 */
@Serializable
data class Bookmark(
    val name: String,
    val uri: String,
    val label: String? = null,
    val icon: String? = null,
    val symbolicIcon: String? = null
) {
    /** The display label shown in the UI — prefers [label] over [name]. */
    val displayName: String get() = label ?: name
}
