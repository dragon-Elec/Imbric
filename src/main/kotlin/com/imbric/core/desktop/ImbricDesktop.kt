package com.imbric.core.desktop

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.backends.gio.GioBackend
import com.imbric.core.ifs.backends.gio.GioRecentBackend
import com.imbric.core.ifs.backends.gio.GioSearchBackend
import com.imbric.core.ifs.backends.gio.support.GioCoroutineBridge

/**
 * Entry point for initializing Imbric with Linux/GNOME desktop integration.
 * Consumers of the library should call [initialize] at startup.
 */
object ImbricDesktop {
    fun initialize() {
        val gio = GioBackend()
        
        // Start the native OS daemon thread pump for GIO async callbacks
        GioCoroutineBridge.startMainContextPump()
        
        // Register standard VFS handlers
        BackendRegistry.register("file", gio)
        BackendRegistry.register("trash", gio)
        BackendRegistry.register("smb", gio)
        BackendRegistry.register("sftp", gio)
        
        // Register specialized Desktop handlers
        BackendRegistry.register("recent", GioRecentBackend())
        BackendRegistry.register("search", GioSearchBackend(gio))
        
        // Set fallback
        BackendRegistry.setDefault(gio)
    }
}
