package com.imbric.core.desktop

import kotlinx.coroutines.flow.StateFlow

/**
 * Abstraction for observing the state of the trash system.
 * Implemented by [TrashMonitor] for native GIO integration.
 */
interface TrashStateProvider {
    /**
     * Observable state of whether the trash is empty.
     */
    val isEmpty: StateFlow<Boolean>

    /**
     * Manually triggers a refresh of the trash state.
     */
    fun refresh()
}
