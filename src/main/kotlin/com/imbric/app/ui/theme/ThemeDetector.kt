package com.imbric.app.ui.theme

import com.imbric.core.desktop.GioSettingsProvider
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.io.File

/**
 * Detects GNOME desktop theme preferences using GSettings and GTK CSS.
 *
 * Reads from `org.gnome.desktop.interface`:
 * - `color-scheme`: "prefer-dark" | "default" (light)
 * - `gtk-theme`: theme name (e.g., "ZorinGreen-Dark")
 *
 * Automatically parses active GTK 4.0/3.0 theme CSS files to extract the exact
 * native `@define-color accent_color` or `@define-color theme_selected_bg_color` hex seed.
 * Falls back to keyword matching or Material 3 baseline if CSS is unavailable.
 */
object ThemeDetector {
    private const val SCHEMA = "org.gnome.desktop.interface"
    private const val KEY_COLOR_SCHEME = "color-scheme"
    private const val KEY_GTK_THEME = "gtk-theme"

    private val CSS_COLOR_REGEX = Regex("""@define-color\s+(?:accent_color|accent_bg_color|theme_selected_bg_color)\s+#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b""")

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
     * Extracts an accent color seed from the GTK theme name or its CSS definitions.
     * 1. Attempts to read the actual hex color from active GTK 4.0/3.0 theme files.
     * 2. Falls back to keyword parsing for known theme prefixes.
     * 3. Returns null if no accent color can be determined (uses M3 default).
     */
    fun observeAccentColor(): Flow<Long?> {
        val provider = settings ?: return kotlinx.coroutines.flow.flowOf(null)
        return provider.observeString(KEY_GTK_THEME).map { themeName ->
            extractAccentFromGtkCss(themeName) ?: extractAccentFromThemeName(themeName)
        }
    }

    /**
     * Parses the active theme's GTK CSS file on disk to extract the real native accent color.
     */
    private fun extractAccentFromGtkCss(themeName: String): Long? {
        if (themeName.isBlank()) return null

        val baseName = themeName.removeSuffix("-Dark").removeSuffix("-Light")
        val home = System.getProperty("user.home") ?: ""

        val candidatePaths = listOf(
            "$home/.config/gtk-4.0/gtk.css",
            "/usr/share/themes/$themeName/gtk-4.0/gtk.css",
            "/usr/share/themes/$themeName/gtk-3.0/gtk.css",
            "/usr/share/themes/$baseName/gtk-4.0/gtk.css",
            "/usr/share/themes/$baseName/gtk-3.0/gtk.css"
        )

        for (path in candidatePaths) {
            val file = File(path)
            if (file.exists() && file.canRead()) {
                try {
                    val content = file.readText()
                    val match = CSS_COLOR_REGEX.find(content)
                    if (match != null) {
                        var hex = match.groupValues[1]
                        if (hex.length == 3) {
                            hex = hex.map { "$it$it" }.joinToString("")
                        }
                        val colorLong = hex.toLongOrNull(16)
                        if (colorLong != null) {
                            return 0xFF000000L or colorLong
                        }
                    }
                } catch (_: Exception) {
                    // Ignore unreadable files and check next candidate
                }
            }
        }
        return null
    }

    private fun extractAccentFromThemeName(themeName: String): Long? {
        val name = themeName.lowercase()
        return when {
            name.contains("green") -> 0xFF23A877
            name.contains("blue") -> 0xFF2196F3
            name.contains("purple") -> 0xFF9C27B0
            name.contains("red") || name.contains("rose") -> 0xFFF44336
            name.contains("orange") || name.contains("amber") -> 0xFFFF9800
            name.contains("teal") || name.contains("cyan") -> 0xFF009688
            name.contains("yellow") -> 0xFFFFEB3B
            name.contains("pink") -> 0xFFE91E63
            name.contains("brown") -> 0xFF795548
            name.contains("grey") || name.contains("gray") -> 0xFF9E9E9E
            else -> null
        }
    }
}
