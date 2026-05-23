package com.imbric.core.desktop.backends

import com.imbric.core.desktop.*
import com.imbric.core.ifs.backends.GioCoroutineBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import org.gnome.gio.*
import org.gnome.glib.GLib
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class GioDesktopEnvironment : DesktopEnvironment {
    init {
        Gio.`javagi$ensureInitialized`()
    }

    private val volumeMonitor: VolumeMonitor by lazy { VolumeMonitor.get() }

    override fun observeDrives(): Flow<List<DesktopDrive>> = callbackFlow {
        val updateDrives = {
            launch {
                val deferreds = volumeMonitor.connectedDrives.mapNotNull { gioDrive ->
                    gioDrive?.let { async { mapDrive(it) } }
                }
                send(deferreds.awaitAll())
            }
            Unit
        }

        // Initial state
        updateDrives()

        // Listen for changes
        val conn1 = volumeMonitor.onDriveConnected { _ -> updateDrives() }
        val conn2 = volumeMonitor.onDriveDisconnected { _ -> updateDrives() }
        val conn3 = volumeMonitor.onDriveChanged { _ -> updateDrives() }
        val conn4 = volumeMonitor.onMountAdded { _ -> updateDrives() }
        val conn5 = volumeMonitor.onMountRemoved { _ -> updateDrives() }
        val conn6 = volumeMonitor.onVolumeAdded { _ -> updateDrives() }
        val conn7 = volumeMonitor.onVolumeRemoved { _ -> updateDrives() }

        awaitClose {
            conn1.disconnect()
            conn2.disconnect()
            conn3.disconnect()
            conn4.disconnect()
            conn5.disconnect()
            conn6.disconnect()
            conn7.disconnect()
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun mount(driveId: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val gioDrive = volumeMonitor.connectedDrives.find { it?.name == driveId }
            if (gioDrive == null) {
                return@withContext Result.failure(Exception("Drive $driveId not found"))
            }
            
            if (!gioDrive.hasVolumes()) {
                return@withContext Result.failure(Exception("Drive has no volumes"))
            }
            
            val volume = gioDrive.volumes.firstOrNull()
            if (volume == null) {
                return@withContext Result.failure(Exception("No volume found on drive"))
            }

            val existingMount = volume.mount
            if (existingMount != null) {
                return@withContext Result.success(existingMount.root.uri ?: "")
            }

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    volume.mount(org.gnome.gio.MountMountFlags.NONE, null, cancellable, callback)
                },
                finish = { result ->
                    volume.mountFinish(result)
                }
            )
            
            val newMount = volume.mount
            val rootUri = newMount?.root?.uri
            if (rootUri != null) {
                Result.success(rootUri)
            } else {
                Result.failure(Exception("Mount finished but mount root URI is null"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun unmount(driveId: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val gioDrive = volumeMonitor.connectedDrives.find { it?.name == driveId }
            val mount = gioDrive?.volumes?.firstOrNull()?.mount
            
            if (mount == null) {
                return@withContext Result.success(Unit) // Already unmounted or doesn't exist
            }

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    mount.unmountWithOperation(org.gnome.gio.MountUnmountFlags.NONE, null, cancellable, callback)
                },
                finish = { result ->
                    mount.unmountWithOperationFinish(result)
                }
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override fun getDefaultApp(mimeType: String): com.imbric.core.desktop.DesktopAppInfo? {
        val gioApp = org.gnome.gio.AppInfo.getDefaultForType(mimeType, false) ?: return null
        return com.imbric.core.desktop.DesktopAppInfo(
            id = gioApp.getId()?.toString() ?: "",
            name = gioApp.getName()?.toString() ?: "",
            executable = gioApp.getExecutable()?.toString() ?: "",
            icon = gioApp.getIcon()?.let { icon ->
                if (icon is org.gnome.gio.ThemedIcon) icon.names?.firstOrNull() else null
            }
        )
    }

    override fun getAllApps(mimeType: String): List<com.imbric.core.desktop.DesktopAppInfo> {
        val gioApps = org.gnome.gio.AppInfo.getAllForType(mimeType)
        val result = mutableListOf<com.imbric.core.desktop.DesktopAppInfo>()
        for (i in 0 until gioApps.size) {
            val gioApp = gioApps.get(i) as? org.gnome.gio.AppInfo ?: continue
            result.add(com.imbric.core.desktop.DesktopAppInfo(
                id = gioApp.getId()?.toString() ?: "",
                name = gioApp.getName()?.toString() ?: "",
                executable = gioApp.getExecutable()?.toString() ?: "",
                icon = gioApp.getIcon()?.let { icon ->
                    if (icon is org.gnome.gio.ThemedIcon) icon.names?.firstOrNull() else null
                }
            ))
        }
        return result
    }

    override suspend fun openFile(uri: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            org.gnome.gio.AppInfo.launchDefaultForUri(uri, null)
            Unit
        }
    }

    override fun observeTheme(): Flow<ThemeMode> = callbackFlow {
        val settings = try { Settings("org.gnome.desktop.interface") } catch (e: Exception) { null }
        
        val updateTheme = {
            val scheme = settings?.getString("color-scheme") ?: "default"
            val mode = when {
                scheme.contains("dark") -> ThemeMode.DARK
                scheme.contains("light") -> ThemeMode.LIGHT
                else -> ThemeMode.SYSTEM
            }
            trySend(mode)
            Unit
        }

        updateTheme()

        val conn = settings?.onChanged(null) { _ ->
            updateTheme()
        }

        awaitClose {
            conn?.disconnect()
        }
    }.flowOn(Dispatchers.IO)

    private suspend fun mapDrive(gioDrive: org.gnome.gio.Drive): DesktopDrive {
        val volume = gioDrive.volumes.firstOrNull()
        val mount = volume?.mount
        val mountUri = mount?.root?.uri
        
        var total = 0L
        var free = 0L
        
        if (mountUri != null) {
            withContext(Dispatchers.IO) {
                try {
                    val gfile = org.gnome.gio.File.newForUri(mountUri)
                    val info = gfile.queryFilesystemInfo("filesystem::size,filesystem::free", null)
                    total = info.getAttributeUint64("filesystem::size")
                    free = info.getAttributeUint64("filesystem::free")
                } catch (e: Exception) {
                    // Ignore FS info errors
                }
            }
        }

        val icon = gioDrive.icon
        val iconName = if (icon is org.gnome.gio.ThemedIcon) icon.names?.firstOrNull() else null

        return DesktopDrive(
            id = gioDrive.getIdentifier("unix-device") ?: gioDrive.name ?: gioDrive.toString(),
            name = gioDrive.name ?: "Unknown Drive",
            icon = iconName,
            isMounted = mount != null,
            mountUri = mountUri,
            totalBytes = total,
            availableBytes = free
        )
    }
}
