package com.imbric.app.aggregators

import com.imbric.core.desktop.*
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.*
import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class DebugAggTest {
    @Test
    fun debug() = runTest {
        val tempDir = createTempDirectory("dbg").toFile()
        val bl = BookmarkList(
            scope = backgroundScope,
            jsonPath = File(tempDir, "b.json").toPath(),
            gtkPath = File(tempDir, "g").toPath(),
            enableMonitoring = false,
            uriValidator = { it.isNotBlank() }
        )
        println("BOOKMARKS_EMIT: ${bl.bookmarks.value}")
        val mounted = DesktopDrive("usb", "USB Stick", null, true, "file:///media/usb")
        val provider = object : VolumeProvider {
            override fun observeDrives() = flowOf(listOf(mounted))
            override suspend fun mount(id: String) = Result.success("")
            override suspend fun unmount(id: String) = Result.success(Unit)
        }
        val dm = DeviceManager(provider, backgroundScope)
        advanceUntilIdle()
        println("DRIVES_EMIT: ${dm.drives.value}")
        val agg = SidebarAggregator(bl, dm, backgroundScope)
        advanceUntilIdle()
        println("SECTIONS: ${agg.sections.value}")
        tempDir.deleteRecursively()
    }
}
