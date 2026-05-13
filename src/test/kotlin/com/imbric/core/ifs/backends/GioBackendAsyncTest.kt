@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.gnome.gio.File
import org.gnome.gio.FileCopyFlags
import org.gnome.glib.GLib
import org.gnome.glib.MainContext
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.test.assertEquals

@Tag("integration")
class GioBackendAsyncTest {

    private val backend = GioBackend()

    @Test
    fun testCopySuspend(@TempDir tempDir: Path) = runTest {
        val srcFile = java.io.File(tempDir.toFile(), "src.txt")
        srcFile.writeText("async copy test")
        val destFile = java.io.File(tempDir.toFile(), "dest.txt")

        val gSrc = File.newForUri("file://${srcFile.absolutePath}")
        val gDest = File.newForUri("file://${destFile.absolutePath}")

        val pumpJob = launch(Dispatchers.Default) {
            val context = MainContext.default_()
            while (isActive) {
                context.iteration(false)
                delay(10)
            }
        }

        with(backend) {
            gSrc.copySuspend(
                gDest,
                FileCopyFlags.NONE,
                GLib.PRIORITY_DEFAULT,
                null,
                null
            )
        }

        pumpJob.cancel()

        assertTrue(destFile.exists(), "Destination file should exist after async copy")
        assertEquals("async copy test", destFile.readText())
    }

    @Test
    fun testMoveSuspend(@TempDir tempDir: Path) = runTest {
        val srcFile = java.io.File(tempDir.toFile(), "src_move.txt")
        srcFile.writeText("async move test")
        val destFile = java.io.File(tempDir.toFile(), "dest_move.txt")

        val gSrc = File.newForUri("file://${srcFile.absolutePath}")
        val gDest = File.newForUri("file://${destFile.absolutePath}")

        val pumpJob = launch(Dispatchers.Default) {
            val context = MainContext.default_()
            while (isActive) {
                context.iteration(false)
                delay(10)
            }
        }

        with(backend) {
            gSrc.moveSuspend(
                gDest,
                FileCopyFlags.NONE,
                GLib.PRIORITY_DEFAULT,
                null,
                null
            )
        }

        pumpJob.cancel()

        assertFalse(srcFile.exists(), "Source file should not exist after async move")
        assertTrue(destFile.exists(), "Destination file should exist after async move")
        assertEquals("async move test", destFile.readText())
    }
}
