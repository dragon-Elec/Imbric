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
    lateinit var registry: BackendRegistry
        private set

    fun initialize(): BackendRegistry {
        val reg = BackendRegistry()
        val gio = GioBackend()
        
        // Start the native OS daemon thread pump for GIO async callbacks
        GioCoroutineBridge.startMainContextPump()
        
        // Register standard VFS handlers
        reg.register("file", gio)
        reg.register("trash", gio)
        reg.register("smb", gio)
        reg.register("sftp", gio)
        
        // Register specialized Desktop handlers
        reg.register("recent", GioRecentBackend())
        reg.register("search", GioSearchBackend(gio))
        
        // Set fallback
        reg.setDefault(gio)

        registry = reg
        return reg
    }
}
