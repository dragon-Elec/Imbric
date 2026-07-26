package com.imbric.core.desktop

import org.gnome.gio.File
import org.gnome.gio.Gio
import java.nio.file.Paths

/**
 * Manages the virtual ~/Desktop directory.
 * Respects XDG user-dirs (e.g., ~/Bureau, ~/桌面) via ~/.config/user-dirs.dirs.
 * Falls back to ~/Desktop on non-XDG systems.
 */
object DesktopDirectory {
    init {
        Gio.`javagi$ensureInitialized`()
    }

    /**
     * Returns the URI of the user's desktop directory (e.g., "file:///home/user/Desktop").
     */
    fun getUri(): String {
        val desktopPath = resolveDesktopPath()
        return "file://$desktopPath"
    }

    /**
     * Resolves the desktop path via XDG user-dirs, falling back to ~/Desktop.
     */
    private fun resolveDesktopPath(): String {
        val userDirsFile = Paths.get(
            System.getProperty("user.home"),
            ".config", "user-dirs.dirs"
        ).toFile()
        if (userDirsFile.exists()) {
            val xdgDesktop = userDirsFile.readLines()
                .firstOrNull { it.startsWith("XDG_DESKTOP_DIR=") }
                ?.substringAfter('=')
                ?.trim('"', '\'')
            if (xdgDesktop != null) {
                return xdgDesktop.replace("\$HOME", System.getProperty("user.home"))
            }
        }
        return System.getProperty("user.home") + "/Desktop"
    }

    /**
     * Returns the desktop directory as a GIO File.
     */
    fun getFile(): File = File.forUri(getUri())

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
