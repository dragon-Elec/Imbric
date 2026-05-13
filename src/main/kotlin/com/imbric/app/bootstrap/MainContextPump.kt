package com.imbric.app.bootstrap

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.withFrameMillis
import kotlinx.coroutines.isActive
import org.gnome.glib.MainContext

/**
 * Synchronizes the GLib MainContext with the Compose frame loop.
 * This ensures that native callbacks (GIO async, signals) fire in sync with the UI.
 *
 * Pattern: Pattern C (MainContext.iteration() Pump) from ref/GIO-COROUTINE-BRIDGE.md
 */
@Composable
fun MainContextPump() {
    LaunchedEffect(Unit) {
        val context = MainContext.default_()
        while (isActive) {
            withFrameMillis {
                // Drain the GLib event loop for this frame.
                // mayBlock = false is crucial to avoid freezing the UI thread.
                while (context.iteration(false)) {
                    // Process all pending native events before next UI frame
                }
            }
        }
    }
}
