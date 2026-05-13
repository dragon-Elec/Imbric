package com.imbric.core.desktop

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.backends.GioBackend
import com.imbric.core.ifs.backends.GioRecentBackend
import com.imbric.core.ifs.backends.GioSearchBackend

/**
 * Entry point for initializing Imbric with Linux/GNOME desktop integration.
 * Consumers of the library should call [initialize] at startup.
 */
object ImbricDesktop {
    fun initialize() {
        val gio = GioBackend()
        
        // Register standard VFS handlers
        BackendRegistry.registerIo("file", gio)
        BackendRegistry.registerIo("trash", gio)
        BackendRegistry.registerIo("smb", gio)
        BackendRegistry.registerIo("sftp", gio)
        
        // Register specialized Desktop handlers
        BackendRegistry.registerIo("recent", GioRecentBackend())
        BackendRegistry.registerIo("search", GioSearchBackend(gio))
        
        // Set fallback
        BackendRegistry.setDefaultIo(gio)
    }
}
