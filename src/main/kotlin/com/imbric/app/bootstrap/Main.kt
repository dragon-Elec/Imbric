package com.imbric.app.bootstrap

import androidx.compose.material3.Text
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import org.gnome.gio.Application
import org.gnome.gio.ApplicationFlags
import org.gnome.gio.Gio
import mu.KotlinLogging

private val logger = KotlinLogging.logger {}

/**
 * Entry point for ImbricFS Desktop.
 *
 * This bootstrap:
 * 1. Initializes the native FFI bindings (java-gi).
 * 2. Registers a GApplication to enable native services (GIO, hardware events).
 * 3. Launches the Compose Multiplatform UI.
 * 4. Perts the native GMainContext into the Compose frame loop (Heartbeat).
 */
fun main(args: Array<String>) {
    // 1. Initialize native bindings
    Gio.`javagi$ensureInitialized`()

    // 2. Register GApplication (Platform Bridge)
    // We register the app ID to enable GIO async operations and hardware signals.
    // We don't call app.run() as it starts a blocking native loop; we pump manually instead.
    val app = Application("com.imbric.ImbricFS", ApplicationFlags.FLAGS_NONE)
    
    try {
        app.register(null)
    } catch (e: Exception) {
        // Fallback: Continue anyway, though some native events might not work.
        logger.warn(e) { "Could not register GApplication: ${e.message}" }
    }

    // 3. Launch Compose UI
    application {
        Window(
            onCloseRequest = ::exitApplication,
            title = "ImbricFS"
        ) {
            // 4. Start the native heartbeat
            // This synchronizes GLib events with the Compose UI loop.
            MainContextPump()
            
            // Initial Placeholder UI
            Text("ImbricFS Heartbeat Active")
        }
    }
}
