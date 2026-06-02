package com.imbric.app.viewmodel

import com.imbric.core.ifs.provider.DirStateRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

/**
 * Represents a single isolated tab or split-pane in the application.
 * Holds the [FileBrowserViewModel] for this specific view and manages its lifecycle.
 */
@OptIn(ExperimentalUuidApi::class)
class PaneContext(
    val id: Uuid = Uuid.random(),
    initialUri: String,
    registry: DirStateRegistry,
    parentScope: CoroutineScope
) {
    // Create a dedicated scope for this pane so it can be cancelled independently
    private val paneScope = CoroutineScope(parentScope.coroutineContext + SupervisorJob(parentScope.coroutineContext[Job]))

    val viewModel = FileBrowserViewModel(
        registry = registry,
        initialUri = initialUri,
        viewModelScope = paneScope
    )

    /**
     * Cleans up resources when this pane (tab) is closed.
     */
    fun destroy() {
        paneScope.cancel("PaneContext $id was closed")
    }
}