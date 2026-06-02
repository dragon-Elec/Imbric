package com.imbric.app.ui.shell

import androidx.compose.runtime.staticCompositionLocalOf
import com.imbric.app.viewmodel.PaneContext

/**
 * Provides the currently active [PaneContext] to the Compose UI tree.
 * Any component can access the active tab's state via `LocalActivePane.current`.
 */
val LocalActivePane = staticCompositionLocalOf<PaneContext> {
    error("No active PaneContext provided. Ensure this is called within a CompositionLocalProvider.")
}