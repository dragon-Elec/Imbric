package com.imbric.core.desktop

import kotlinx.coroutines.flow.Flow

/** System theme (dark/light) observation. */
interface ThemeProvider {
    fun observeTheme(): Flow<ThemeMode>
}
