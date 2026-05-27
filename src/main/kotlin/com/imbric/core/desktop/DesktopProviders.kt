package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

/**
 * A reactive wrapper for system settings.
 * Allows the application to observe and react to system preference changes.
 */
interface SettingsProvider {
    val schemaId: String
    fun observeBoolean(key: String): Flow<Boolean>
    fun observeString(key: String): Flow<String>
    fun observeInt(key: String): Flow<Int>
    fun setBoolean(key: String, value: Boolean)
    fun setString(key: String, value: String)
    fun setInt(key: String, value: Int)
}

/**
 * Abstraction for observing starred files.
 */
interface StarredStateProvider {
    val starredUris: StateFlow<Set<String>>
    fun isStarred(uri: String): Boolean
    suspend fun toggleStarred(uri: String): Result<Boolean>
}

/**
 * Abstraction for observing the state of the trash system.
 * Implemented by TrashMonitor for native GIO integration.
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

/**
 * Abstraction for observing desktop links.
 */
interface DesktopLinkProvider {
    val links: StateFlow<List<DesktopLink>>
    fun refresh()
}
