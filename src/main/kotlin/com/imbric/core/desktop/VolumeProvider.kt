package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow

/** Hardware volumes: observe plugged-in drives, mount, unmount. */
interface VolumeProvider {
    fun observeDrives(): Flow<List<DesktopDrive>>
    suspend fun mount(driveId: String): Result<String>
    suspend fun unmount(driveId: String): Result<Unit>
}
