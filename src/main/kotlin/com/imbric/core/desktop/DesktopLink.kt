package com.imbric.core.desktop

/**
 * Represents a desktop link (like GNOME's .desktop files in ~/Desktop).
 * These are the virtual icons on the desktop: Computer, Home, Trash, Network, etc.
 * Ported from nautilus-desktop-link.c / NautilusDesktopLink.
 */
data class DesktopLink(
    val id: String,
    val name: String,
    val uri: String,
    val icon: String,
    val symbolicIcon: String? = null,
    val linkType: DesktopLinkType
)

enum class DesktopLinkType {
    /** "Computer" — shows mounted volumes and filesystem root */
    COMPUTER,
    /** "Home" — user's home directory */
    HOME,
    /** "Trash" — trash folder */
    TRASH,
    /** "Network" — network locations */
    NETWORK,
    /** User-created desktop shortcut */
    SHORTCUT
}
