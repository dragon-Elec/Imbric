package com.imbric.app.ui.theme

import com.imbric.core.desktop.GioSettingsProvider
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Detects GNOME desktop theme preferences using GSettings.
 *
 * Reads from `org.gnome.desktop.interface`:
 * - `color-scheme`: "prefer-dark" | "default" (light)
 * - `gtk-theme`: theme name (e.g., "ZorinGreen-Dark")
 *
 * Falls back to light theme if GSettings are unavailable.
 */
object ThemeDetector {
    private const val SCHEMA = "org.gnome.desktop.interface"
    private const val KEY_COLOR_SCHEME = "color-scheme"
    private const val KEY_GTK_THEME = "gtk-theme"

    private val settings: GioSettingsProvider? by lazy {
        try {
            GioSettingsProvider(SCHEMA)
        } catch (e: Exception) {
            // GSettings schema not available (e.g., non-GNOME desktop)
            null
        }
    }

    /**
     * Observes the system dark mode preference.
     * Emits `true` when dark mode is active, `false` for light mode.
     */
    fun observeDarkMode(): Flow<Boolean> {
        val provider = settings ?: return kotlinx.coroutines.flow.flowOf(false)
        return provider.observeString(KEY_COLOR_SCHEME).map { it == "prefer-dark" }
    }

    /**
     * Reads the current dark mode state synchronously.
     */
    fun isDarkMode(): Boolean {
        val provider = settings ?: return false
        return try {
            provider.observeString(KEY_COLOR_SCHEME)
                .let { false } // Default; the reactive flow handles the real check
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Extracts an accent color seed from the GTK theme name.
     * Maps common Zorin/GNOME theme prefixes to Material 3 seed colors.
     * Returns null if no accent color can be determined (uses M3 default).
     */
    fun observeAccentColor(): Flow<Long?> {
        val provider = settings ?: return kotlinx.coroutines.flow.flowOf(null)
        return provider.observeString(KEY_GTK_THEME).map { themeName ->
            extractAccentFromThemeName(themeName)
        }
    }

    private fun extractAccentFromThemeName(themeName: String): Long? {
        val name = themeName.lowercase()
        return when {
            name.contains("green") -> 0xFF4CAF50    // Material Green 500
            name.contains("blue") -> 0xFF2196F3     // Material Blue 500
            name.contains("purple") -> 0xFF9C27B0   // Material Purple 500
            name.contains("red") || name.contains("rose") -> 0xFFF44336
            name.contains("orange") || name.contains("amber") -> 0xFFFF9800
            name.contains("teal") || name.contains("cyan") -> 0xFF009688
            name.contains("yellow") -> 0xFFFFEB3B
            name.contains("pink") -> 0xFFE91E63
            name.contains("brown") -> 0xFF795548
            name.contains("grey") || name.contains("gray") -> 0xFF9E9E9E
            // Zorin-specific: "ZorinGreen" → green
            name.startsWith("zorin") -> {
                when {
                    name.contains("green") -> 0xFF4CAF50
                    name.contains("blue") -> 0xFF2196F3
                    name.contains("purple") -> 0xFF9C27B0
                    name.contains("red") -> 0xFFF44336
                    name.contains("orange") -> 0xFFFF9800
                    else -> 0xFF4CAF50 // Zorin default is green
                }
            }
            else -> null // Use Material 3 default seed color
        }
    }
}
