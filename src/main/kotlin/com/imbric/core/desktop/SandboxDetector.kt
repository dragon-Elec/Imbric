package com.imbric.core.desktop

/**
 * Detects whether the application is running inside a sandboxed environment.
 * Sandboxed environments (Flatpak, Snap) restrict file system access and
 * require special handling for certain operations.
 * Ported from nautilus-sandbox.c
 */
object SandboxDetector {
    /** True if running inside a Flatpak sandbox. */
    val isFlatpak: Boolean by lazy {
        System.getenv("FLATPAK_ID") != null ||
        java.io.File("/.flatpak-info").exists()
    }

    /** True if running inside a Snap sandbox. */
    val isSnap: Boolean by lazy {
        System.getenv("SNAP") != null
    }

    /** True if running inside any sandbox. */
    val isSandboxed: Boolean by lazy {
        isFlatpak || isSnap
    }

    /**
     * Returns the sandbox type string, or null if not sandboxed.
     */
    val sandboxType: String? by lazy {
        when {
            isFlatpak -> "flatpak"
            isSnap -> "snap"
            else -> null
        }
    }
}
