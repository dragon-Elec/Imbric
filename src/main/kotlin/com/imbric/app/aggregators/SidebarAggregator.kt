package com.imbric.app.aggregators

import com.imbric.core.desktop.BookmarkList
import com.imbric.core.desktop.DeviceManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

data class SidebarItem(
    val label: String,
    val iconName: String,
    val uri: String,
    val isEjectable: Boolean = false
)

data class SidebarSection(
    val title: String,
    val items: List<SidebarItem>
)

/**
 * Pure data transformer.
 * Listens to raw data streams from the core engine (Bookmarks, Drives)
 * and merges them into a unified UI model for the Sidebar.
 */
class SidebarAggregator(
    bookmarks: BookmarkList,
    devices: DeviceManager,
    scope: CoroutineScope
) {
    val sections: StateFlow<List<SidebarSection>> = combine(
        bookmarks.bookmarks,
        devices.drives
    ) { bms, drives ->
        val sections = mutableListOf<SidebarSection>()

        // 1. Quick Access (Bookmarks)
        if (bms.isNotEmpty()) {
            sections.add(
                SidebarSection(
                    title = "Quick Access",
                    items = bms.map { bm ->
                        SidebarItem(
                            label = bm.displayName,
                            iconName = bm.icon ?: "folder",
                            uri = bm.uri
                        )
                    }
                )
            )
        }

        // 2. Volumes (Drives)
        if (drives.isNotEmpty()) {
            sections.add(
                SidebarSection(
                    title = "Volumes",
                    items = drives.map { drive ->
                        SidebarItem(
                            label = drive.name,
                            iconName = drive.icon ?: "drive-harddisk",
                            uri = drive.mountUri ?: "",
                            isEjectable = drive.isMounted
                        )
                    }.filter { it.uri.isNotEmpty() }
                )
            )
        }

        sections
    }.stateIn(scope, SharingStarted.Eagerly, emptyList())
}