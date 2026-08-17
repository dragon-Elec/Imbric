package com.imbric.app.ui.theme

import androidx.compose.ui.graphics.Color
import com.materialkolor.PaletteStyle
import com.materialkolor.dynamiccolor.ColorSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

enum class ThemeMode(val label: String) {
    SYSTEM("System"),
    LIGHT("Light"),
    DARK("Dark")
}

data class ColorPreset(
    val name: String,
    val color: Color
)

object ThemePresets {
    val presets = listOf(
        ColorPreset("Mint", Color(0xFFBBF1DD)),
        ColorPreset("Emerald", Color(0xFF23A877)),
        ColorPreset("Sapphire", Color(0xFF2196F3)),
        ColorPreset("Violet", Color(0xFF9C27B0)),
        ColorPreset("Ruby", Color(0xFFF44336)),
        ColorPreset("Amber", Color(0xFFFF9800)),
        ColorPreset("Teal", Color(0xFF009688)),
        ColorPreset("Rose", Color(0xFFE91E63)),
        ColorPreset("Slate", Color(0xFF607D8B)),
        ColorPreset("Baseline Purple", Color(0xFF6750A4))
    )
}

data class ThemeConfig(
    val mode: ThemeMode = ThemeMode.SYSTEM,
    val specVersion: ColorSpec.SpecVersion = ColorSpec.SpecVersion.SPEC_2025,
    val style: PaletteStyle = PaletteStyle.Vibrant,
    val customSeed: Color? = null,
    val contrastLevel: Double = 0.0,
    val isAmoled: Boolean = false
)

/**
 * Global reactive controller for Imbric's live dynamic theme settings.
 */
object ThemeController {
    private val _config = MutableStateFlow(ThemeConfig())
    val config: StateFlow<ThemeConfig> = _config.asStateFlow()

    private val _isPanelOpen = MutableStateFlow(false)
    val isPanelOpen: StateFlow<Boolean> = _isPanelOpen.asStateFlow()

    fun togglePanel() {
        _isPanelOpen.update { !it }
    }

    fun setPanelOpen(open: Boolean) {
        _isPanelOpen.value = open
    }

    fun setMode(mode: ThemeMode) {
        _config.update { it.copy(mode = mode) }
    }

    fun setSpecVersion(specVersion: ColorSpec.SpecVersion) {
        _config.update { it.copy(specVersion = specVersion) }
    }

    fun setStyle(style: PaletteStyle) {
        _config.update { it.copy(style = style) }
    }

    fun setCustomSeed(color: Color?) {
        _config.update { it.copy(customSeed = color) }
    }

    fun setContrastLevel(contrast: Double) {
        _config.update { it.copy(contrastLevel = contrast.coerceIn(-1.0, 1.0)) }
    }

    fun setAmoled(isAmoled: Boolean) {
        _config.update { it.copy(isAmoled = isAmoled) }
    }

    fun resetToDefaults() {
        _config.value = ThemeConfig()
    }
}
