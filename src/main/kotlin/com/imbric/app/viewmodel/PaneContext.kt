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
     *
     * Cancels the pane scope first so its collectors stop, then releases this
     * pane's pin on the directory it was viewing. Without the release the
     * DirState — its GFile monitor, enrichment workers and full listing —
     * would stay alive under the window scope until LRU eviction.
     *
     * The pipeline timer is cleared last. [FileBrowserViewModel.pipelineTimer]
     * writes through to the *shared* [DirStateRegistry], so a timer installed by
     * a pane that is closed mid-navigation would otherwise stay stamped on every
     * DirState and keep collecting marks from all remaining tabs. The normal
     * clear path (`onReportDone`) only ever runs for the pane that is composed —
     * i.e. the active one — so a closed or navigated-away pane never reaches it.
     * `viewModel` is null for Home panes, hence the safe call.
     */
    fun destroy() {
        paneScope.cancel("PaneContext $id was closed")
        // Release the viewer's actual pin, not a snapshot of currentUri: a navigation
        // emission may not have been collected yet, in which case currentUri names a
        // URI this pane never pinned (leaking the real one) or never collected.
        viewModel?.releasePin()
        // Clear the timer only if this pane owns one. The setter writes through to the
        // SINGLE shared registry field, so an unconditional null from a pane that never
        // had a timer (idle background tab closing) clobbers another pane's live trace
        // mid-load — the next getOrCreate would stamp null onto its DirState.
        if (viewModel?.pipelineTimer != null) {
            viewModel.pipelineTimer = null
        }
    }
}
