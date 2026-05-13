package com.imbric.core.desktop

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.*

/**
 * High-level manager for hardware devices and volumes.
 * UI should consume [drives] to show the sidebar list.
 */
class DeviceManager(
    private val environment: DesktopEnvironment,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
) {
    /**
     * Live stream of connected drives.
     */
    val drives: StateFlow<List<DesktopDrive>> = environment.observeDrives()
        .stateIn(scope, SharingStarted.Eagerly, emptyList())

    /**
     * Request to mount a drive.
     */
    suspend fun mount(drive: DesktopDrive): Result<String> {
        return environment.mount(drive.id)
    }

    /**
     * Request to unmount/eject a drive.
     */
    suspend fun unmount(drive: DesktopDrive): Result<Unit> {
        return environment.unmount(drive.id)
    }
}
