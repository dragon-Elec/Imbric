package com.imbric.app.bootstrap

import androidx.compose.runtime.*
import com.imbric.app.aggregators.HomeAggregator
import com.imbric.app.aggregators.SidebarAggregator
import com.imbric.app.ui.shell.MainWindow
import com.imbric.app.viewmodel.ShellViewModel
import com.imbric.core.desktop.BookmarkList
import com.imbric.core.desktop.DeviceManager
import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.directories.DirStateRegistry
import kotlin.uuid.ExperimentalUuidApi

/**
 * Root composable for Imbric.
 * Acts as the application controller, holding the high-level ViewModel
 * and Aggregator lifecycles, and rendering the MainWindow layout.
 */
@OptIn(ExperimentalUuidApi::class)
@Composable
fun ImbricApp(
    registry: DirStateRegistry,
    backendRegistry: BackendRegistry,
    deviceManager: DeviceManager,
    bookmarkList: BookmarkList
) {
    val scope = rememberCoroutineScope()
    val shellViewModel = remember { ShellViewModel(registry, scope) }

    val sidebarAggregator = remember { SidebarAggregator(bookmarkList, deviceManager, scope) }
    val sidebarSections by sidebarAggregator.sections.collectAsState()

    val homeAggregator = remember { HomeAggregator(backendRegistry, bookmarkList, deviceManager, scope) }

    MainWindow(
        shellViewModel = shellViewModel,
        sidebarSections = sidebarSections,
        homeState = homeAggregator.state
    )
}
