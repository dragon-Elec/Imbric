package com.imbric.core.desktop

/** Default application lookup and file opening. */
interface AppLauncher {
    fun getDefaultApp(mimeType: String): DesktopAppInfo?
    fun getAllApps(mimeType: String): List<DesktopAppInfo>
    suspend fun openFile(uri: String): Result<Unit>
}
