@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.ifs.backends.TestUtils.withGlibPump
import com.imbric.core.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import com.imbric.core.testing.BashHelper
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
            BashHelper.runScript("echo -n 'async copy test' > src.txt", tempDir.toFile())
            val srcUri = "file://${tempDir.toAbsolutePath()}/src.txt"
            val destUri = "file://${tempDir.toAbsolutePath()}/dest.txt"

            val gSrc = File.newForUri(srcUri)
            val gDest = File.newForUri(destUri)

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gSrc.copyAsync(gDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                },
                finish = { result ->
                    gSrc.copyFinish(result)
                }
            )

            val destFile = java.io.File(tempDir.toFile(), "dest.txt")
            assertTrue(destFile.exists(), "Destination file should exist after async copy")
            assertEquals("async copy test", destFile.readText())
        }
    }

    @Test
    fun testMoveAsync(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("echo -n 'async move test' > src_move.txt", tempDir.toFile())
            val srcUri = "file://${tempDir.toAbsolutePath()}/src_move.txt"
            val destUri = "file://${tempDir.toAbsolutePath()}/dest_move.txt"

            val gSrc = File.newForUri(srcUri)
            val gDest = File.newForUri(destUri)

            GioCoroutineBridge.awaitGioAsync(
                block = { cancellable, callback ->
                    gSrc.moveAsync(gDest, FileCopyFlags.NONE, GLib.PRIORITY_DEFAULT, cancellable, null, callback)
                },
                finish = { result ->
                    gSrc.moveFinish(result)
                }
            )

            val srcFile = java.io.File(tempDir.toFile(), "src_move.txt")
            assertFalse(srcFile.exists(), "Source file should not exist after async move")
            val destFile = java.io.File(tempDir.toFile(), "dest_move.txt")
            assertTrue(destFile.exists(), "Destination file should exist after async move")
            assertEquals("async move test", destFile.readText())
        }
    }

    @Test
    fun testCopyWithProgress(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("dd if=/dev/zero of=src_large.txt bs=1024 count=100", tempDir.toFile())
            val srcUri = "file://${tempDir.toAbsolutePath()}/src_large.txt"
            val destUri = "file://${tempDir.toAbsolutePath()}/dest_large.txt"

            val gSrc = File.newForUri(srcUri)
            val gDest = File.newForUri(destUri)

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

            val destFile = java.io.File(tempDir.toFile(), "dest_large.txt")
            assertTrue(destFile.exists(), "Destination file should exist after async copy")
            assertTrue(progressCalled, "Progress callback should have been called")
            assertTrue(lastCurrent > 0, "Progress should have reported bytes copied")
        }
    }

    @Test
    fun testRecursiveMoveAsync(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val backend = GioBackend()
            
            BashHelper.runScript("""
                mkdir -p root/sub
                echo -n "recursive move test" > root/sub/file.txt
            """.trimIndent(), tempDir.toFile())
            
            val rootUri = "file://${tempDir.toAbsolutePath()}/root"
            val destUri = "file://${tempDir.toAbsolutePath()}/root_moved"
            
            val job = FileJob(
                id = Uuid.random(),
                opType = "move",
                source = rootUri,
                dest = destUri
            )
            
            // Execute move
            val progress = mutableListOf<TransferProgress>()
            backend.move(job).collect {
                progress.add(it)
            }
            
            // Verify
            val rootDir = java.io.File(tempDir.toFile(), "root")
            assertFalse(rootDir.exists(), "Source root should be gone")
            
            val destDir = java.io.File(tempDir.toFile(), "root_moved")
            assertTrue(destDir.exists(), "Destination root should exist")
            val movedFile = java.io.File(destDir, "sub/file.txt")
            assertTrue(movedFile.exists(), "Nested file should exist in destination")
            assertEquals("recursive move test", movedFile.readText())
            
            // Verify we got progress events
            assertTrue(progress.isNotEmpty(), "Should have received progress events")
            assertTrue(progress.any { it.inversePayload != null }, "Should have received an undo action for undo")
        }
    }

    @Test
    fun testSearchWithQuery(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val backend = GioBackend()
            
            BashHelper.runScript("""
                echo -n "content" > match_1.txt
                echo -n "content" > match_2.log
                echo -n "content" > other.txt
                mkdir sub
                echo -n "content" > sub/match_3.txt
            """.trimIndent(), tempDir.toFile())

            val rootUri = "file://${tempDir.toAbsolutePath()}"

            // 1. Basic search
            val query1 = VfsQuery(text = "match", rootUri = rootUri)
            val results1 = backend.search(query1).toList().flatten()
            assertEquals(3, results1.size)
            assertTrue(results1.any { it.uri == "$rootUri/match_1.txt" }, "Should find match_1.txt with correct URI")
            assertTrue(results1.any { it.uri == "$rootUri/match_2.log" }, "Should find match_2.log with correct URI")
            assertTrue(results1.any { it.uri == "$rootUri/sub/match_3.txt" }, "Should find sub/match_3.txt with correct URI")

            // 2. MIME filter
            val query2 = VfsQuery(text = "match", rootUri = rootUri, mimeFilter = "text/plain")
            val results2 = backend.search(query2).toList().flatten()
            // Note: .log might be text/plain or text/x-log depending on system
            assertTrue(results2.size >= 2, "Should find at least 2 text files")

            // 3. Non-recursive
            val query3 = VfsQuery(text = "match", rootUri = rootUri, recursive = false)
            val results3 = backend.search(query3).toList().flatten()
            assertEquals(2, results3.size)
        }
    }
}
