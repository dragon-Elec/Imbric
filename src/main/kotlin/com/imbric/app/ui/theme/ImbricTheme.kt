package com.imbric.app.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import com.materialkolor.DynamicMaterialTheme
import com.materialkolor.PaletteStyle
import com.materialkolor.dynamiccolor.ColorSpec

/**
 * Imbric's Material 3 theme composable.
 *
 * Automatically detects GNOME dark/light mode via [ThemeDetector] and applies
 * the appropriate Material 3 color scheme. If an accent color is detected from
 * the GTK theme name, it uses the MaterialKolor library to generate a true
 * Monet (Material You) HCT tonal palette from that seed color.
 *
 * All Material 3 components (Text, Button, Surface, etc.) automatically inherit
 * the theme tokens — no manual decoration needed.
 *
 * @param content The composable content to theme.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImbricTheme(
    content: @Composable () -> Unit
) {
    // Observe system dark mode preference
    val isDarkSystem by ThemeDetector.observeDarkMode().collectAsState(initial = false)

    // Observe accent color from GTK theme name
    val accentSeed by ThemeDetector.observeAccentColor().collectAsState(initial = null)

    // Observe live theme configuration
    val config by ThemeController.config.collectAsState()

    val isDark = when (config.mode) {
        ThemeMode.SYSTEM -> isDarkSystem
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }

    val seedColor = config.customSeed ?: accentSeed?.let { Color(it) } ?: Color(0xFF6750A4)

    // DynamicMaterialTheme uses Google's Material Color Utilities (HCT color science)
    // to generate the full 30+ color tonal palette (primary, secondary, surface, etc.)
    // from the single seed color, giving us true Monet dynamic colors on Desktop.
    DynamicMaterialTheme(
        seedColor = seedColor,
        isDark = isDark,
        isAmoled = config.isAmoled,
        style = config.style,
        specVersion = config.specVersion,
        contrastLevel = config.contrastLevel,
        animate = true, // Smoothly animate theme changes
        typography = DesktopTypography,
        shapes = DesktopShapes,
    ) {
        // Enforce desktop interactive component sizing across the entire app.
        // Drops Android's 48dp minimum touch-target enforcement for all M3 components.
        CompositionLocalProvider(
            LocalMinimumInteractiveComponentSize provides Dp.Unspecified,
            content = content
        )
    }
}
