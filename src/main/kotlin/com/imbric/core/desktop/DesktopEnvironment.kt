package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow

/**
 * Global system states and operations that are NOT tied to a specific URI.
 * This is the bridge between the app and the Host OS Desktop Environment.
 */
interface DesktopEnvironment {
    // --- Volumes & Mounts ---
    /**
     * Observe plugged-in hardware (USB sticks, SD cards, external HDDs).
     */
    fun observeDrives(): Flow<List<DesktopDrive>>
    
    /**
     * Request the OS to mount a specific drive.
     * Returns the root URI of the mounted volume (e.g. "file:///media/ray/USB").
     */
    suspend fun mount(driveId: String): Result<String>
    
    /**
     * Request the OS to unmount/eject a drive.
     */
    suspend fun unmount(driveId: String): Result<Unit>

    // --- Application Launching ---
    /**
     * Get the default application for a specific MIME type.
     */
    fun getDefaultApp(mimeType: String): DesktopAppInfo?
    
    /**
     * Get all installed applications that support a specific MIME type.
     */
    fun getAllApps(mimeType: String): List<DesktopAppInfo>
    
    /**
     * Open a file or folder using the OS-default application.
     */
    suspend fun openFile(uri: String): Result<Unit>

    // --- System Preferences ---
    /**
     * Observe the system's current theme (Dark/Light).
     */
    fun observeTheme(): Flow<ThemeMode>
}

data class DesktopDrive(
    val id: String,
    val name: String,
    val icon: String?,
    val isMounted: Boolean,
    val mountUri: String? = null,
    val totalBytes: Long = 0,
    val availableBytes: Long = 0
)

data class DesktopAppInfo(
    val id: String,
    val name: String,
    val executable: String,
    val icon: String?
)

enum class ThemeMode {
    LIGHT, DARK, SYSTEM
}
