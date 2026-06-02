package com.imbric.app.viewmodel

import com.imbric.core.ifs.provider.DirStateRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

/**
 * The global Window Manager.
 * Manages the list of open tabs ([PaneContext]s) and tracks which one is currently active.
 */
@OptIn(ExperimentalUuidApi::class)
class ShellViewModel(
    private val registry: DirStateRegistry,
    private val shellScope: CoroutineScope,
    initialUri: String = "file:///"
) {
    private val _tabs = MutableStateFlow<List<PaneContext>>(emptyList())
    val tabs: StateFlow<List<PaneContext>> = _tabs.asStateFlow()

    private val _activePaneId = MutableStateFlow<Uuid?>(null)
    val activePaneId: StateFlow<Uuid?> = _activePaneId.asStateFlow()

    init {
        // Start with one default tab
        addTab(initialUri)
    }

    /**
     * Opens a new tab and makes it active.
     */
    fun addTab(uri: String) {
        val newPane = PaneContext(
            initialUri = uri,
            registry = registry,
            parentScope = shellScope
        )
        _tabs.update { it + newPane }
        _activePaneId.value = newPane.id
    }

    /**
     * Closes a tab. If it was the active tab, falls back to the previous tab.
     */
    fun closeTab(id: Uuid) {
        val currentTabs = _tabs.value
        if (currentTabs.size <= 1) return // Don't close the last tab

        val tabToClose = currentTabs.find { it.id == id } ?: return
        val index = currentTabs.indexOf(tabToClose)

        // Determine the new active tab if we are closing the currently active one
        if (_activePaneId.value == id) {
            val newActiveIndex = if (index > 0) index - 1 else 1
            _activePaneId.value = currentTabs[newActiveIndex].id
        }

        // Remove and destroy
        _tabs.update { it.filterNot { pane -> pane.id == id } }
        tabToClose.destroy()
    }

    /**
     * Switches the active tab.
     */
    fun setActiveTab(id: Uuid) {
        if (_tabs.value.any { it.id == id }) {
            _activePaneId.value = id
        }
    }
}