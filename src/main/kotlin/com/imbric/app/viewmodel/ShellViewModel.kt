package com.imbric.app.viewmodel

import com.imbric.core.ifs.directories.DirStateRegistry
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
    initialTab: TabType = TabType.Home
) {
    private val _tabs = MutableStateFlow<List<PaneContext>>(emptyList())
    val tabs: StateFlow<List<PaneContext>> = _tabs.asStateFlow()

    private val _activePaneId = MutableStateFlow<Uuid?>(null)
    val activePaneId: StateFlow<Uuid?> = _activePaneId.asStateFlow()

    init {
        // Start with one default tab
        addTab(initialTab)
    }

    /**
     * Opens a new tab and makes it active.
     * Defaults to a [TabType.Home] dashboard tab.
     */
    fun addTab(type: TabType = TabType.Home) {
        val newPane = PaneContext(
            type = type,
            registry = registry,
            parentScope = shellScope
        )
        _tabs.update { it + newPane }
        _activePaneId.value = newPane.id
    }

    /**
     * Navigates the active pane to a folder.
     * Folder panes navigate in place (preserving their back stack);
     * Home panes convert into a fresh Folder pane.
     */
    fun openFolder(uri: String) {
        val currentTabs = _tabs.value
        val activeIndex = currentTabs.indexOfFirst { it.id == _activePaneId.value }
        if (activeIndex == -1) return

        val old = currentTabs[activeIndex]
        val vm = old.viewModel
        if (vm != null) {
            vm.navigateTo(uri)
            return
        }

        // Home pane → convert to a Folder pane (same tab id, fresh lifecycle)
        old.destroy()
        val folderPane = PaneContext(
            id = old.id,
            type = TabType.Folder(uri),
            registry = registry,
            parentScope = shellScope
        )
        _tabs.update { tabs -> tabs.mapIndexed { i, pane -> if (i == activeIndex) folderPane else pane } }
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
