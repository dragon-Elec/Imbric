package com.imbric.core.desktop

import kotlinx.coroutines.flow.StateFlow

/**
 * Abstraction for observing desktop links.
 */
interface DesktopLinkProvider {
    val links: StateFlow<List<DesktopLink>>
    fun refresh()
}