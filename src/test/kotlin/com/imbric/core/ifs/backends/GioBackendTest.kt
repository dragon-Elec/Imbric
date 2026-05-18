@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.FileJob
import com.imbric.core.ifs.backends.TestUtils.withGlibPump
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import org.gnome.glib.MainContext
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.*
import com.imbric.core.ifs.VfsConflictException
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
            val file1 = java.io.File(tempDir.toFile(), "alpha.txt")
            val file2 = java.io.File(tempDir.toFile(), "beta.txt")

            file1.writeText("hello")
            file2.writeText("world")

            val subDir = java.io.File(tempDir.toFile(), "subdir")
            subDir.mkdir()

            assertTrue(backend.exists("file://${file1.absolutePath}"))
            assertFalse(backend.exists("file://${tempDir.toAbsolutePath()}/missing.txt"))

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
            assertEquals(5L, alphaInfo?.size)
        }
    }

    @Test
    fun testPhysicalMetadata(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val file = java.io.File(tempDir.toFile(), "metadata_target.txt")
            file.writeText("metadata test content")
            val fileUri = "file://${file.absolutePath}"

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
            val target = java.io.File(tempDir.toFile(), "target.txt")
            target.writeText("target")

            val link = tempDir.resolve("link.txt")
            Files.createSymbolicLink(link, target.toPath())

            val linkUri = "file://${link.toAbsolutePath()}"
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
            val src = tempDir.resolve("src")
            val dest = tempDir.resolve("dest")
            Files.createDirectory(src)
            Files.createDirectory(src.resolve("subdir"))
            Files.writeString(src.resolve("file.txt"), "hello")
            Files.writeString(src.resolve("subdir/inner.txt"), "world")

            val job = FileJob(
                id = Uuid.random(),
                opType = "copy",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}"
            )

            backend.copy(job).toList()

            assertTrue(Files.exists(dest))
            assertTrue(Files.exists(dest.resolve("file.txt")))
            assertTrue(Files.exists(dest.resolve("subdir/inner.txt")))
            assertEquals("hello", Files.readString(dest.resolve("file.txt")))
            assertEquals("world", Files.readString(dest.resolve("subdir/inner.txt")))
        }
    }

    @Test
    fun testRecursiveMove(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val src = tempDir.resolve("src")
            val dest = tempDir.resolve("dest")
            Files.createDirectory(src)
            Files.createDirectory(src.resolve("subdir"))
            Files.writeString(src.resolve("file.txt"), "hello")

            val job = FileJob(
                id = Uuid.random(),
                opType = "move",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}"
            )

            backend.move(job).toList()

            assertTrue(Files.exists(dest))
            assertTrue(Files.exists(dest.resolve("file.txt")))
            assertTrue(Files.exists(dest.resolve("subdir")))
            assertFalse(Files.exists(src), "Source directory should be deleted after move")
        }
    }

    @Test
    fun testCopyConflictThrowsVfsException(@TempDir tempDir: Path) = runTest {
        withGlibPump {
            val src = tempDir.resolve("src.txt")
            val dest = tempDir.resolve("dest.txt")
            Files.writeString(src, "source")
            Files.writeString(dest, "destination")

            val job = FileJob(
                id = Uuid.random(),
                opType = "copy",
                source = "file://${src.toAbsolutePath()}",
                dest = "file://${dest.toAbsolutePath()}",
                overwrite = false
            )

            val exception = assertFailsWith<VfsConflictException> {
                backend.copy(job).toList()
            }
            assertEquals(VfsConflictException.EXISTS, exception.code)
        }
    }
}
