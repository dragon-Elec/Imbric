package com.imbric.core.desktop.backends

import com.imbric.core.desktop.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
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
            val drives = volumeMonitor.connectedDrives.mapNotNull { it?.let { mapDrive(it) } }
            trySend(drives)
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
        runCatching {
            kotlinx.coroutines.suspendCancellableCoroutine<String> { cont ->
                val gioDrive = volumeMonitor.connectedDrives.find { it?.name == driveId }
                if (gioDrive == null) {
                    cont.resumeWithException(Exception("Drive $driveId not found"))
                    return@suspendCancellableCoroutine
                }
                
                if (!gioDrive.hasVolumes()) {
                    cont.resumeWithException(Exception("Drive has no volumes"))
                    return@suspendCancellableCoroutine
                }
                
                val volume = gioDrive.volumes.firstOrNull()
                if (volume == null) {
                    cont.resumeWithException(Exception("No volume found on drive"))
                    return@suspendCancellableCoroutine
                }

                if (volume.mount != null) {
                    cont.resume(volume.mount!!.root.uri)
                    return@suspendCancellableCoroutine
                }

                val callback = AsyncReadyCallback { source, result, _ ->
                    try {
                        val v = source as org.gnome.gio.Volume
                        v.mountFinish(result)
                        val newMount = v.mount
                        if (newMount != null) {
                            cont.resume(newMount.root.uri)
                        } else {
                            cont.resumeWithException(Exception("Mount finished but mount object is null"))
                        }
                    } catch (e: Exception) {
                        cont.resumeWithException(e)
                    }
                }
                
                GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
                    volume.mount(org.gnome.gio.MountMountFlags.NONE, null, null, callback)
                    false
                }
            }
        }
    }

    override suspend fun unmount(driveId: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            kotlinx.coroutines.suspendCancellableCoroutine<Unit> { cont ->
                val gioDrive = volumeMonitor.connectedDrives.find { it?.name == driveId }
                val mount = gioDrive?.volumes?.firstOrNull()?.mount
                
                if (mount == null) {
                    cont.resume(Unit) // Already unmounted or doesn't exist
                    return@suspendCancellableCoroutine
                }

                val callback = AsyncReadyCallback { source, result, _ ->
                    try {
                        val m = source as org.gnome.gio.Mount
                        m.unmountWithOperationFinish(result)
                        cont.resume(Unit)
                    } catch (e: Exception) {
                        cont.resumeWithException(e)
                    }
                }
                
                GLib.idleAdd(GLib.PRIORITY_DEFAULT) {
                    mount.unmountWithOperation(org.gnome.gio.MountUnmountFlags.NONE, null, null, callback)
                    false
                }
            }
        }
    }

    override fun getDefaultApp(mimeType: String): DesktopAppInfo? {
        val gioApp = org.gnome.gio.AppInfo.getDefaultForType(mimeType, false) ?: return null
        return DesktopAppInfo(
            id = gioApp.id ?: "",
            name = gioApp.name ?: "",
            executable = gioApp.executable ?: "",
            icon = gioApp.icon?.toString()
        )
    }

    override fun getAllApps(mimeType: String): List<DesktopAppInfo> {
        val gioApps = org.gnome.gio.AppInfo.getAllForType(mimeType)
        val result = mutableListOf<DesktopAppInfo>()
        for (i in 0 until gioApps.size) {
            val gioApp = gioApps.get(i) as? org.gnome.gio.AppInfo ?: continue
            result.add(DesktopAppInfo(
                id = gioApp.id ?: "",
                name = gioApp.name ?: "",
                executable = gioApp.executable ?: "",
                icon = gioApp.icon?.toString()
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
        trySend(ThemeMode.SYSTEM)
        awaitClose { }
    }

    private fun mapDrive(gioDrive: org.gnome.gio.Drive): DesktopDrive {
        val volume = gioDrive.volumes.firstOrNull()
        val mount = volume?.mount
        val mountUri = mount?.root?.uri
        
        var total = 0L
        var free = 0L
        
        if (mountUri != null) {
            try {
                val gfile = org.gnome.gio.File.newForUri(mountUri)
                val info = gfile.queryFilesystemInfo("filesystem::size,filesystem::free", null)
                total = info.getAttributeUint64("filesystem::size")
                free = info.getAttributeUint64("filesystem::free")
            } catch (e: Exception) {
                // Ignore FS info errors
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
