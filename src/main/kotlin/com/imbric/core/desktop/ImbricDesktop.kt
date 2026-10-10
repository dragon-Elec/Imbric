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
    /**
     * Guards against a second [initialize]. Initialization is not idempotent by nature: it
     * starts a GLib main-context pump thread (GioCoroutineBridge.startMainContextPump) and
     * replaces the [registry] singleton, so a repeat call would either spawn a duplicate pump
     * or hand out a registry that the already-running UI never sees.
     *
     * Written only after [registry] is published, so a concurrent caller either loses the
     * race (and observes the fresh instance) or observes a fully initialized one.
     */
    @Volatile
    private var initialized = false

    lateinit var registry: BackendRegistry
        private set

    @Synchronized
    fun initialize(): BackendRegistry {
        if (initialized) return registry

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
        initialized = true
        return reg
    }
}
