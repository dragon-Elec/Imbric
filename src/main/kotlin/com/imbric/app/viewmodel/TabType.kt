package com.imbric.app.viewmodel

/**
 * The type of content a [PaneContext] displays.
 *
 * A tab is either:
 *  - [Home]: the widget dashboard (own state model, NOT a directory)
 *  - [Folder]: a classic file browser rooted at [Folder.uri]
 *
 * URIs belong to directories — the Home page is not a directory and
 * must not be modeled as one.
 */
sealed interface TabType {
    /** The widget dashboard. No URI, no DirState, no directory listing. */
    data object Home : TabType

    /** A classic file browser tab rooted at the given [uri]. */
    data class Folder(val uri: String) : TabType
}
