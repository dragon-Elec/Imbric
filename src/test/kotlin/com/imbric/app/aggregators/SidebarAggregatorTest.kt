@file:OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package com.imbric.app.aggregators

import com.imbric.core.desktop.BookmarkList
import com.imbric.core.desktop.DesktopDrive
import com.imbric.core.desktop.DeviceManager
import com.imbric.core.desktop.VolumeProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Behavioral tests for the sidebar aggregation.
 *
 * Regression focus: unmounted drives (mountUri == null) must NEVER produce a
 * sidebar item with an empty URI — clicking one previously called
 * navigateTo("") which crashed/froze the GUI (ct100/ct500 class of bug).
 */
class SidebarAggregatorTest {

    private lateinit var tempDir: File
    private lateinit var bookmarkList: BookmarkList

    @BeforeTest
    fun setup() {
        tempDir = createTempDirectory("sidebar-test").toFile()
        val jsonFile = File(tempDir, "bookmarks.json")
        val gtkFile = File(tempDir, "gtk-bookmarks")
        bookmarkList = BookmarkList(
            scope = CoroutineScope(UnconfinedTestDispatcher() + SupervisorJob()),
            jsonPath = jsonFile.toPath(),
            gtkPath = gtkFile.toPath(),
            enableMonitoring = false,
            uriValidator = { it.isNotBlank() }
        )
    }

    @AfterTest
    fun teardown() {
        bookmarkList.dispose()
        tempDir.deleteRecursively()
    }

    /**
     * Builds an aggregator on a dedicated scope so its stateIn/combine
     * coroutines can be cancelled deterministically at test end.
     * [advanceUntilIdle] propagates the drive flow before assertions read
     * [SidebarAggregator.sections].
     */
    private class AggFixture(
        val aggregator: SidebarAggregator,
        val scope: kotlinx.coroutines.CoroutineScope
    )

    private fun kotlinx.coroutines.test.TestScope.makeAggregator(drives: List<DesktopDrive>): AggFixture {
        val aggScope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + SupervisorJob())
        val fakeProvider = object : VolumeProvider {
            override fun observeDrives() = flowOf(drives)
            override suspend fun mount(driveId: String) = Result.success("")
            override suspend fun unmount(driveId: String) = Result.success(Unit)
        }
        val manager = DeviceManager(fakeProvider, aggScope)
        val aggregator = SidebarAggregator(bookmarkList, manager, aggScope)
        advanceUntilIdle()
        return AggFixture(aggregator, aggScope)
    }

    private fun kotlinx.coroutines.test.TestScope.volumesFor(drives: List<DesktopDrive>): List<SidebarItem> {
        val fixture = makeAggregator(drives)
        val items = fixture.aggregator.sections.value
            .find { it.title == "Volumes" }
            ?.items
            ?: emptyList()
        fixture.scope.cancel()
        return items
    }

    @Test
    fun `unmounted drive with null mountUri is excluded from sidebar`() = runTest {
        val unmounted = DesktopDrive(
            id = "ct500",
            name = "CT500",
            icon = null,
            isMounted = false,
            mountUri = null
        )

        val items = volumesFor(listOf(unmounted))
        assertTrue(
            items.isEmpty(),
            "Unmounted drive must not produce a sidebar item: $items"
        )
    }

    @Test
    fun `mounted drive appears with its mount URI`() = runTest {
        val mounted = DesktopDrive(
            id = "usb-1",
            name = "USB Stick",
            icon = null,
            isMounted = true,
            mountUri = "file:///media/usb"
        )

        val items = volumesFor(listOf(mounted))
        assertEquals(1, items.size)
        assertEquals("USB Stick", items[0].label)
        assertEquals("file:///media/usb", items[0].uri)
    }

    @Test
    fun `mixed mounted and unmounted only shows navigable drives`() = runTest {
        val unmounted = DesktopDrive("nvme", "CT500", null, false, null)
        val mounted = DesktopDrive("usb", "USB Stick", null, true, "file:///media/usb")

        val items = volumesFor(listOf(unmounted, mounted))
        assertEquals(1, items.size, "Only mounted drive should be listed")
        assertEquals("USB Stick", items[0].label)
        assertEquals("file:///media/usb", items[0].uri)
    }

    @Test
    fun `empty URI never appears even with blank mountUri`() = runTest {
        // Defensive: a drive reporting mounted=true but with a blank URI
        // must also be excluded — navigateTo("") is the crash path.
        val blank = DesktopDrive("weird", "Blank", null, true, "   ")

        val items = volumesFor(listOf(blank))
        assertFalse(
            items.any { it.uri.isBlank() },
            "Blank URI must never reach the sidebar: $items"
        )
    }
}
