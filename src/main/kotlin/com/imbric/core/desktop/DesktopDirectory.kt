package com.imbric.core.desktop

import org.gnome.gio.File
import org.gnome.gio.Gio

/**
 * Manages the virtual ~/Desktop directory.
 * On GNOME, the desktop directory is typically ~/Desktop or ~/桌面 (localized).
 * Ported from nautilus-desktop-directory.c
 */
object DesktopDirectory {
    init {
        Gio.`javagi$ensureInitialized`()
    }

    /**
     * Returns the URI of the user's desktop directory (e.g., "file:///home/user/Desktop").
     */
    fun getUri(): String {
        val desktopPath = System.getProperty("user.home") + "/Desktop"
        return "file://$desktopPath"
    }

    /**
     * Returns the desktop directory as a GIO File.
     */
    fun getFile(): File = File.newForUri(getUri())

    /**
     * Returns true if the desktop directory exists.
     */
    fun exists(): Boolean = getFile().queryExists(null)

    /**
     * Creates the desktop directory if it doesn't exist.
     */
    fun ensureExists(): Boolean {
        val file = getFile()
        if (!file.queryExists(null)) {
            try {
                file.makeDirectoryWithParents(null)
                return true
            } catch (e: Exception) {
                return false
            }
        }
        return true
    }
}
