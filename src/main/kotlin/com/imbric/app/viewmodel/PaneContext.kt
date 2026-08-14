package com.imbric.app.viewmodel

import com.imbric.core.ifs.directories.DirStateRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

/**
 * Represents a single isolated tab or split-pane in the application.
 *
 * A pane is either a [TabType.Home] widget dashboard (no viewModel — it has
 * its own state model) or a [TabType.Folder] file browser (viewModel holds
 * the [FileBrowserViewModel] for that URI).
 */
@OptIn(ExperimentalUuidApi::class)
class PaneContext(
    val id: Uuid = Uuid.random(),
    val type: TabType,
    private val registry: DirStateRegistry,
    parentScope: CoroutineScope
) {
    // Create a dedicated scope for this pane so it can be cancelled independently
    private val paneScope = CoroutineScope(parentScope.coroutineContext + SupervisorJob(parentScope.coroutineContext[Job]))

    /** The file browser view model — present only for [TabType.Folder] panes. */
    val viewModel: FileBrowserViewModel? = when (type) {
        is TabType.Home -> null
        is TabType.Folder -> FileBrowserViewModel(registry, type.uri, paneScope)
    }

    /** True when this pane displays the Home widget dashboard. */
    val isHome: Boolean get() = type is TabType.Home

    /** True when this pane displays a folder listing. */
    val isFolder: Boolean get() = type is TabType.Folder

    /**
     * Cleans up resources when this pane (tab) is closed.
     */
    fun destroy() {
        paneScope.cancel("PaneContext $id was closed")
    }
}
