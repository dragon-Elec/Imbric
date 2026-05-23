@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.FileJob
import com.imbric.core.ifs.backends.TestUtils.withGlibPump
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import com.imbric.core.testing.BashHelper
import org.gnome.glib.MainContext
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.*

import kotlin.uuid.Uuid

@Tag("integration")
class GioBackendTest {

    private val backend = GioBackend()

    /**
     * Runs [block] with a background GLib main context pump.
     * Required for any test that triggers GIO async operations (copy, move).
     */
    @Test
    fun testPhysicalListAndExists(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val dirUri = "file://${tempDir.toAbsolutePath()}"
            BashHelper.runScript("""
                echo -n "hello" > alpha.txt
                echo -n "world" > beta.txt
                mkdir subdir
            """.trimIndent(), tempDir.toFile())

            assertTrue(backend.exists("$dirUri/alpha.txt"))
            assertFalse(backend.exists("$dirUri/missing.txt"))

            val children = backend.list(dirUri).toList()

            assertEquals(3, children.size, "Should find 2 files and 1 subdir")
            val names = children.map { it.name }.toSet()
            assertTrue(names.contains("alpha.txt"))
            assertTrue(names.contains("beta.txt"))
            assertTrue(names.contains("subdir"))

            val subdirInfo = children.find { it.name == "subdir" }
            assertTrue(subdirInfo?.isDirectory == true)

            val alphaInfo = children.find { it.name == "alpha.txt" }
            assertTrue(alphaInfo?.isDirectory == false)
            // echo -n gives exactly 5 bytes
            assertEquals(5L, alphaInfo?.size)
        }
    }

    @Test
    fun testPhysicalMetadata(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("echo -n 'metadata test content' > metadata_target.txt", tempDir.toFile())
            val fileUri = "file://${tempDir.toAbsolutePath()}/metadata_target.txt"

            val result = backend.getMetadata(fileUri)
            assertTrue(result.isSuccess)

            val info = result.getOrThrow()
            assertEquals("metadata_target.txt", info.name)
            assertFalse(info.isDirectory)
            assertFalse(info.isSymlink)
            assertEquals(21L, info.size)
            assertTrue(info.isWritable)
        }
    }

    @Test
    fun testPhysicalSymlinkMetadata(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("""
                echo -n "target" > target.txt
                ln -s target.txt link.txt
            """.trimIndent(), tempDir.toFile())

            val linkUri = "file://${tempDir.toAbsolutePath()}/link.txt"
            val result = backend.getMetadata(linkUri)

            assertTrue(result.isSuccess)
            val info = result.getOrThrow()

            assertEquals("link.txt", info.name)
            assertTrue(info.isSymlink)
            assertTrue(info.symlinkTarget?.contains("target.txt") == true)
        }
    }

    @Test
    fun testRecursiveCopy(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("""
                mkdir -p src/subdir
                echo -n "hello" > src/file.txt
                echo -n "world" > src/subdir/inner.txt
            """.trimIndent(), tempDir.toFile())

            val src = tempDir.resolve("src")
            val dest = tempDir.resolve("dest")

            val job = FileJob(
                id = Uuid.random(),
                opType = "copy",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}"
            )

            backend.copy(job).toList()

            assertTrue(dest.toFile().exists())
            assertTrue(dest.resolve("file.txt").toFile().exists())
            assertTrue(dest.resolve("subdir/inner.txt").toFile().exists())
            assertEquals("hello", dest.resolve("file.txt").toFile().readText())
            assertEquals("world", dest.resolve("subdir/inner.txt").toFile().readText())
        }
    }

    @Test
    fun testRecursiveMove(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("""
                mkdir -p src/subdir
                echo -n "hello" > src/file.txt
            """.trimIndent(), tempDir.toFile())

            val src = tempDir.resolve("src")
            val dest = tempDir.resolve("dest")

            val job = FileJob(
                id = Uuid.random(),
                opType = "move",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}"
            )

            backend.move(job).toList()

            assertTrue(dest.toFile().exists())
            assertTrue(dest.resolve("file.txt").toFile().exists())
            assertTrue(dest.resolve("subdir").toFile().exists())
            assertEquals("hello", dest.resolve("file.txt").toFile().readText())
            assertFalse(src.toFile().exists(), "Source directory should be deleted after move")
        }
    }

    @Test
    fun testCopyConflictThrowsVfsException(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            BashHelper.runScript("""
                echo -n "source" > src.txt
                echo -n "destination" > dest.txt
            """.trimIndent(), tempDir.toFile())

            val src = tempDir.resolve("src.txt")
            val dest = tempDir.resolve("dest.txt")

            val job = FileJob(
                id = Uuid.random(),
                opType = "copy",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}",
                overwrite = false
            )

            val exception = assertFailsWith<com.imbric.core.models.VfsError.AlreadyExists> {
                backend.copy(job).toList()
            }
            // The URI in the error should be the source URI
            assertEquals("file://${src.toAbsolutePath()}", exception.uri)
        }
    }
}
