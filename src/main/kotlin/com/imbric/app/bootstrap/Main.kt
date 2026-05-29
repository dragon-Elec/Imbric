package com.imbric.app.bootstrap

import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import com.imbric.app.ui.theme.ImbricTheme
import com.imbric.core.desktop.ImbricDesktop
import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.provider.DirState
import com.imbric.core.ifs.provider.DirStateRegistry
import org.gnome.gio.Gio
import mu.KotlinLogging
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.isActive

private val logger = KotlinLogging.logger {}

/**
 * Entry point for ImbricFS Desktop.
 *
 * Bootstrap sequence:
 * 1. Initialize native FFI bindings (java-gi).
 * 2. Initialize all desktop backends via [ImbricDesktop].
 * 3. Launch Compose Multiplatform UI with GLib heartbeat.
 */
fun main(args: Array<String>) {
    println("[BOOT] Starting Imbric...")

    // 1. Initialize native GIO bindings
    // This must happen before any GIO classes are loaded.
    try {
        println("[BOOT] Initializing GIO...")
        Gio.`javagi$ensureInitialized`()
        
        println("[BOOT] Initializing desktop backends...")
        ImbricDesktop.initialize()
    } catch (e: Exception) {
        println("[BOOT] Fatal initialization error: ${e.message}")
        e.printStackTrace()
        return
    }

    if (args.isNotEmpty()) {
        val target = args[0]
        val cleanTarget = if (!target.contains("://") && !target.startsWith("/")) {
            java.io.File(target).absolutePath
        } else {
            target
        }

        println("[CLI] Diagnostic Mode Active")
        println("[CLI] Emulating App Layer VFS Consumer...")
        
        val defaultBackend = BackendRegistry.getDefaultIo()
        if (defaultBackend == null) {
            println("[CLI] Error: No default VFS Backend registered")
            return
        }

        try {
            kotlinx.coroutines.runBlocking {
                // Note: GLib MainContext pump is already started natively by ImbricDesktop.initialize()

                val defaultBackend = BackendRegistry.getDefaultIo()
                requireNotNull(defaultBackend) { "No default IOBackend registered" }
                val dirState = DirState(args[0], defaultBackend, this)
                
                try {
                    kotlinx.coroutines.withTimeout(10000) {
                        dirState.isLoading.combine(dirState.items) { isLoading, items ->
                            println("[CLI STATE CHANGE] isLoading = $isLoading | items count = ${items.size}")
                            if (!isLoading) {
                                println("[CLI STATE COMPLETE] Final listing of files:")
                                items.forEachIndexed { index, file ->
                                    println("  [$index] Name: ${file.name}")
                                    println("       URI:  ${file.uri}")
                                    println("       Mime: ${file.mimeType}")
                                }
                                throw kotlinx.coroutines.CancellationException("Success")
                            }
                        }.collect()
                    }
                } catch (e: kotlinx.coroutines.CancellationException) {
                    if (e.message != "Success") throw e
                } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
                    println("[CLI] 🚨 TIMEOUT EXCEEDED! State Flow got stuck.")
                } finally {
                    dirState.destroy()
                }
            }
            println("[CLI] Done.")
        } catch (e: Exception) {
            println("[CLI] Fatal error during consumer emulation: ${e.message}")
            e.printStackTrace()
        }
        return
    }

    // 2. Launch Compose UI
    println("[BOOT] Launching Compose UI...")
    application {
        Window(
            onCloseRequest = ::exitApplication,
            title = "Imbric"
        ) {
            // GLib ↔ Compose frame sync (Disabled in favor of native OS daemon thread pump)
            // MainContextPump()

            val scope = rememberCoroutineScope()
            val defaultBackend = BackendRegistry.getDefaultIo()
            requireNotNull(defaultBackend) { "No default IOBackend registered" }
            
            // In a real app, this would be provided by a DI container (like Koin)
            val registry = remember { DirStateRegistry(defaultBackend, scope) }

            ImbricTheme {
                ImbricApp(registry)
            }
        }
    }
}
