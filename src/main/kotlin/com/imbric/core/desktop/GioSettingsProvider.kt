package com.imbric.core.desktop

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.onStart
import org.gnome.gio.Settings
import org.gnome.gio.Gio

/**
 * A reactive wrapper for GSettings.
 * Allows the application to observe and react to system preference changes.
 */
class GioSettingsProvider(override val schemaId: String) : SettingsProvider {
    init {
        Gio.`javagi$ensureInitialized`()
    }

    private val settings = Settings(schemaId)

    /**
     * Observes changes to a specific boolean setting.
     */
    override fun observeBoolean(key: String): Flow<Boolean> = callbackFlow {
        val conn = settings.onChanged(key) { _ ->
            trySend(settings.getBoolean(key))
        }
        
        awaitClose {
            conn.disconnect()
        }
    }.onStart { emit(settings.getBoolean(key)) }

    /**
     * Observes changes to a specific string setting.
     */
    override fun observeString(key: String): Flow<String> = callbackFlow {
        val conn = settings.onChanged(key) { _ ->
            trySend(settings.getString(key) ?: "")
        }
        
        awaitClose {
            conn.disconnect()
        }
    }.onStart { emit(settings.getString(key) ?: "") }

    /**
     * Observes changes to a specific integer setting.
     */
    override fun observeInt(key: String): Flow<Int> = callbackFlow {
        val conn = settings.onChanged(key) { _ ->
            trySend(settings.getInt(key))
        }
        
        awaitClose {
            conn.disconnect()
        }
    }.onStart { emit(settings.getInt(key)) }

    /**
     * Sets a boolean setting.
     */
    override fun setBoolean(key: String, value: Boolean) {
        settings.setBoolean(key, value)
    }

    /**
     * Sets a string setting.
     */
    override fun setString(key: String, value: String) {
        settings.setString(key, value)
    }

    /**
     * Sets an integer setting.
     */
    override fun setInt(key: String, value: Int) {
        settings.setInt(key, value)
    }
}
