package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow

/**
 * @deprecated Use [VolumeProvider], [AppLauncher], and [ThemeProvider] directly.
 */
@Deprecated("Use VolumeProvider, AppLauncher, and ThemeProvider directly")
interface DesktopEnvironment : VolumeProvider, AppLauncher, ThemeProvider

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
