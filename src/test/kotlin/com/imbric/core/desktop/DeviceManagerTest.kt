package com.imbric.core.desktop

import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

class DeviceManagerTest {

    private class FakeDesktopEnvironment : DesktopEnvironment {
        override fun observeDrives() = flowOf(listOf(
            DesktopDrive("usb-1", "USB Stick", null, true, "file:///media/usb")
        ))
        override suspend fun mount(driveId: String) = Result.success("file:///media/usb")
        override suspend fun unmount(driveId: String) = Result.success(Unit)
        override fun getDefaultApp(mimeType: String) = DesktopAppInfo("vlc", "VLC", "vlc", null)
        override fun getAllApps(mimeType: String) = listOf(DesktopAppInfo("vlc", "VLC", "vlc", null))
        override suspend fun openFile(uri: String) = Result.success(Unit)
        override fun observeTheme() = flowOf(ThemeMode.DARK)
    }

    @Test
    fun testDrivesStream() = runTest {
        val manager = DeviceManager(FakeDesktopEnvironment(), this)
        // StateFlow needs a moment or a collector to start
        val drives = manager.drives.filter { it.isNotEmpty() }.first()
        assertEquals(1, drives.size)
        assertEquals("USB Stick", drives[0].name)
    }

    @Test
    fun testMount() = runTest {
        val manager = DeviceManager(FakeDesktopEnvironment(), this)
        val drive = DesktopDrive("usb-1", "USB Stick", null, false)
        val result = manager.mount(drive)
        assertEquals("file:///media/usb", result.getOrNull())
    }
}
