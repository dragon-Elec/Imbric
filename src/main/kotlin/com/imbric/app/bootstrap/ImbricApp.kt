package com.imbric.app.bootstrap

import androidx.compose.runtime.*
import com.imbric.app.aggregators.SidebarAggregator
import com.imbric.app.ui.shell.MainWindow
import com.imbric.app.viewmodel.ShellViewModel
import com.imbric.core.desktop.BookmarkList
import com.imbric.core.desktop.DeviceManager
import com.imbric.core.ifs.provider.DirStateRegistry
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
    deviceManager: DeviceManager,
    bookmarkList: BookmarkList
) {
    val scope = rememberCoroutineScope()
    val initialUri = "file:///home/ray/Pictures/empty folder"
    val shellViewModel = remember { ShellViewModel(registry, scope, initialUri) }

    val sidebarAggregator = remember { SidebarAggregator(bookmarkList, deviceManager, scope) }
    val sidebarSections by sidebarAggregator.sections.collectAsState()

    MainWindow(
        shellViewModel = shellViewModel,
        sidebarSections = sidebarSections
    )
}