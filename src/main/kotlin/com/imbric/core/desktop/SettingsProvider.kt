package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow

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