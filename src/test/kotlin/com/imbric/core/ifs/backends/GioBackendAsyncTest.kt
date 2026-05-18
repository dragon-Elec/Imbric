@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.ifs.backends.TestUtils.withGlibPump
import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.gnome.gio.File
import org.gnome.gio.FileCopyFlags
import org.gnome.glib.GLib
import org.gnome.glib.MainContext
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.test.assertEquals
import kotlin.uuid.Uuid

@Tag("integration")
class GioBackendAsyncTest {

    @BeforeEach
    fun setup() {
        org.gnome.gio.Gio.`javagi$ensureInitialized`()
    }

    @Test
    fun testCopyAsync(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val srcFile = java.io.File(tempDir.toFile(), "src.txt")
            srcFile.writeText("async copy test")
            val destFile = java.io.File(tempDir.toFile(), "dest.txt")

            val gSrc = File.newForUri("file://${srcFile.absolutePath}")
            val gDest = File.newForUri("file://${destFile.absolutePath}")

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gSrc.copyAsync(gDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                },
                finish = { result ->
                    gSrc.copyFinish(result)
                }
            )

            assertTrue(destFile.exists(), "Destination file should exist after async copy")
            assertEquals("async copy test", destFile.readText())
        }
    }

    @Test
    fun testMoveAsync(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val srcFile = java.io.File(tempDir.toFile(), "src_move.txt")
            srcFile.writeText("async move test")
            val destFile = java.io.File(tempDir.toFile(), "dest_move.txt")

            val gSrc = File.newForUri("file://${srcFile.absolutePath}")
            val gDest = File.newForUri("file://${destFile.absolutePath}")

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gSrc.moveAsync(gDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                },
                finish = { result ->
                    gSrc.moveFinish(result)
                }
            )

            assertFalse(srcFile.exists(), "Source file should not exist after async move")
            assertTrue(destFile.exists(), "Destination file should exist after async move")
            assertEquals("async move test", destFile.readText())
        }
    }

    @Test
    fun testCopyWithProgress(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val srcFile = java.io.File(tempDir.toFile(), "src_large.txt")
            srcFile.writeBytes(ByteArray(1024 * 100) { it.toByte() }) // 100KB
            val destFile = java.io.File(tempDir.toFile(), "dest_large.txt")

            val gSrc = File.newForUri("file://${srcFile.absolutePath}")
            val gDest = File.newForUri("file://${destFile.absolutePath}")

            var progressCalled = false
            var lastCurrent = 0L

            val progressCallback = org.gnome.gio.FileProgressCallback { current, total, _ ->
                progressCalled = true
                lastCurrent = current
            }

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gSrc.copyAsync(gDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, progressCallback, callback)
                },
                finish = { result ->
                    gSrc.copyFinish(result)
                }
            )

            assertTrue(destFile.exists(), "Destination file should exist after async copy")
            assertTrue(progressCalled, "Progress callback should have been called")
            assertTrue(lastCurrent > 0, "Progress should have reported bytes copied")
        }
    }

    @Test
    fun testRecursiveMoveAsync(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val backend = GioBackend()
            
            // Create a deep tree: root/sub/file.txt
            val rootDir = java.io.File(tempDir.toFile(), "root")
            rootDir.mkdir()
            val subDir = java.io.File(rootDir, "sub")
            subDir.mkdir()
            val file = java.io.File(subDir, "file.txt")
            file.writeText("recursive move test")
            
            val destDir = java.io.File(tempDir.toFile(), "root_moved")
            
            val job = FileJob(
                id = Uuid.random(),
                opType = "move",
                source = "file://${rootDir.absolutePath}",
                dest = "file://${destDir.absolutePath}"
            )
            
            // Execute move
            val progress = mutableListOf<TransferProgress>()
            backend.move(job).collect {
                progress.add(it)
            }
            
            // Verify
            assertFalse(rootDir.exists(), "Source root should be gone")
            assertTrue(destDir.exists(), "Destination root should exist")
            val movedFile = java.io.File(destDir, "sub/file.txt")
            assertTrue(movedFile.exists(), "Nested file should exist in destination")
            assertEquals("recursive move test", movedFile.readText())
            
            // Verify we got progress events
            assertTrue(progress.isNotEmpty(), "Should have received progress events")
            assertTrue(progress.any { it.inversePayload != null }, "Should have received an inverse payload for undo")
        }
    }

    @Test
    fun testSearchWithQuery(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val backend = GioBackend()
            
            // Create files
            val rootDir = tempDir.toFile()
            java.io.File(rootDir, "match_1.txt").writeText("content")
            java.io.File(rootDir, "match_2.log").writeText("content")
            java.io.File(rootDir, "other.txt").writeText("content")
            
            val subDir = java.io.File(rootDir, "sub")
            subDir.mkdir()
            java.io.File(subDir, "match_3.txt").writeText("content")

            // 1. Basic search
            val query1 = VfsQuery(text = "match", rootUri = "file://${rootDir.absolutePath}")
            val results1 = backend.search(query1).toList()
            assertEquals(3, results1.size)

            // 2. MIME filter
            val query2 = VfsQuery(text = "match", rootUri = "file://${rootDir.absolutePath}", mimeFilter = "text/plain")
            val results2 = backend.search(query2).toList()
            // Note: .log might be text/plain or text/x-log depending on system
            assertTrue(results2.size >= 2, "Should find at least 2 text files")

            // 3. Non-recursive
            val query3 = VfsQuery(text = "match", rootUri = "file://${rootDir.absolutePath}", recursive = false)
            val results3 = backend.search(query3).toList()
            assertEquals(2, results3.size)
        }
    }
}
