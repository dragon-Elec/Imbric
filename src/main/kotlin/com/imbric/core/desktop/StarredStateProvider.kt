package com.imbric.core.desktop

import kotlinx.coroutines.flow.StateFlow

/**
 * Abstraction for observing starred files.
 */
interface StarredStateProvider {
    val starredUris: StateFlow<Set<String>>
    fun isStarred(uri: String): Boolean
    suspend fun toggleStarred(uri: String): Result<Boolean>
}