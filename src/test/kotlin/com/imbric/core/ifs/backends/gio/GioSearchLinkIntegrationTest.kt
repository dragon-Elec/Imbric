@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends.gio

import com.imbric.core.models.FileJob
import com.imbric.core.models.VfsError
import com.imbric.core.models.VfsQuery
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Symlink semantics for search, listing, deepCount, copy and delete.
 *
 * Search recurses into symlinks (a NOFOLLOW enumeration reports
 * SYMBOLIC_LINK for links, so the isSymlink check is what lets a
 * link-to-dir be walked); copy/deepCount semantics are unchanged —
 * these tests pin them.
 */
@Tag("integration")
class GioSearchLinkIntegrationTest {

    private val backend = GioBackend()

    @Test
    fun `search recurses into linked directories`(@TempDir tempDir: Path) = runTest {
        val sub = File(tempDir.toFile(), "sub").also { it.mkdir() }
        File(sub, "needle.txt").writeText("content")
        Files.createSymbolicLink(tempDir.resolve("linked"), sub.toPath())
        val root = "file://${tempDir.toAbsolutePath()}"

        val results = backend.search(VfsQuery(text = "needle", rootUri = root)).toList().flatten()

        // The target's contents are reachable through the link,
        // with the row carrying the link path.
        val throughLink = results.filter { it.uri.startsWith("$root/linked/") }
        assertTrue(
            throughLink.any { it.name == "needle.txt" },
            "search must find target contents through the link, got: ${results.map { it.uri }}"
        )
    }

    @Test
    fun `search terminates on cyclic links`(@TempDir tempDir: Path) = runTest {
        val dirA = File(tempDir.toFile(), "dirA").also { it.mkdir() }
        val dirB = File(tempDir.toFile(), "dirB").also { it.mkdir() }
        // a→b→a: every traversal of the cycle spends one symlink
        // hop, so the walk is bounded and must terminate.
        Files.createSymbolicLink(dirA.toPath().resolve("linkB"), dirB.toPath())
        Files.createSymbolicLink(dirB.toPath().resolve("linkA"), dirA.toPath())
        val root = "file://${dirA.absolutePath}"

        // Completes instead of hanging; the links themselves match.
        val results = backend.search(VfsQuery(text = "link", rootUri = root)).toList().flatten()
        assertTrue(results.isNotEmpty(), "the links themselves should match")
        assertTrue(results.all { it.isSymlink }, "only links should match here")
    }

    @Test
    fun `link-to-dir lists with directory shape`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val sub = File(tempDir.toFile(), "sub").also { it.mkdir() }
            File(sub, "inner.txt").writeText("x")
            Files.createSymbolicLink(tempDir.resolve("linked"), sub.toPath())

            val children = backend.list("file://${tempDir.toAbsolutePath()}")
            val link = children.single { it.name == "linked" }
            assertTrue(link.isSymlink)
            // The follow-query resolves the target's type, so a
            // link-to-dir lists as a directory (Nautilus parity).
            assertTrue(link.isDirectory, "link-to-dir must list as a directory")
            assertEquals("inode/directory", link.mimeType)
            assertEquals(0L, link.size)
        }
    }

    @Test
    fun `deepCount counts a link as one file without following`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val sub = File(tempDir.toFile(), "sub").also { it.mkdir() }
            File(sub, "nested.txt").writeText("12345")
            File(tempDir.toFile(), "real.txt").writeText("abc")
            Files.createSymbolicLink(tempDir.resolve("linked"), sub.toPath())
            val root = "file://${tempDir.toAbsolutePath()}"

            val final = backend.deepCount(root).toList().last()

            // 1 dir (sub), 3 files (real.txt, nested.txt, and
            // the link as its own entry). The link contributes
            // only its own size — GIO reports 0 for it on
            // Linux listings — and the target tree is never
            // double-counted: nested.txt's 5 bytes appear
            // exactly once. Following the link would give
            // directories=2 and totalSize >= 13.
            assertEquals(1, final.directories)
            assertEquals(3, final.files)
            assertTrue(
                final.totalSize in 8L..12L,
                "real.txt (3) + nested.txt (5) counted once, link adds only its own size: ${final.totalSize}"
            )
        }
    }

    @Test
    fun `copy follows a link, delete of the link stays link-only`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val target = File(tempDir.toFile(), "target.txt")
            target.writeText("payload")
            Files.createSymbolicLink(tempDir.resolve("link.txt"), target.toPath())
            val root = "file://${tempDir.toAbsolutePath()}"

            // Copy follows the link (pre-existing behavior): the
            // copy is a regular file carrying the target's content.
            backend.copy(
                FileJob(opType = "copy", source = "$root/link.txt", dest = "$root/copy.txt")
            ).toList()
            val copy = File(tempDir.toFile(), "copy.txt")
            assertTrue(copy.isFile, "copy of a link follows to a regular file")
            assertEquals("payload", copy.readText())

            // Deleting the copy touches neither the target nor the link.
            backend.delete(FileJob(opType = "delete", source = "$root/copy.txt"))
            assertTrue(target.isFile)
            assertTrue(File(tempDir.toFile(), "link.txt").exists())

            // Deleting the link removes only the link.
            backend.delete(FileJob(opType = "delete", source = "$root/link.txt"))
            assertFalse(File(tempDir.toFile(), "link.txt").exists())
            assertTrue(target.isFile, "the target survives link deletion")
            assertEquals("payload", target.readText())
        }
    }

    @Test
    fun `navigating into a link keeps the link path`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val sub = File(tempDir.toFile(), "sub").also { it.mkdir() }
            File(sub, "inner.txt").writeText("x")
            Files.createSymbolicLink(tempDir.resolve("linked"), sub.toPath())
            val root = "file://${tempDir.toAbsolutePath()}"

            val children = backend.list("$root/linked")
            val inner = children.single { it.name == "inner.txt" }
            assertTrue(
                inner.uri.startsWith("$root/linked/"),
                "children of a link keep the link path: ${inner.uri}"
            )
        }
    }

    @Test
    fun `search does not double-emit a diamond target`(@TempDir tempDir: Path) = runTest {
        val sub = File(tempDir.toFile(), "sub").also { it.mkdir() }
        File(sub, "needle.txt").writeText("x")
        // Two routes to the same target: the walk reaches needle.txt
        // twice, but the result-side dedup must emit it once.
        Files.createSymbolicLink(tempDir.resolve("linkA"), sub.toPath())
        Files.createSymbolicLink(tempDir.resolve("linkB"), sub.toPath())
        val root = "file://${tempDir.toAbsolutePath()}"

        val results = backend.search(VfsQuery(text = "needle", rootUri = root)).toList().flatten()
        val hits = results.filter { it.name == "needle.txt" }
        assertEquals(1, hits.size, "diamond must emit the target once, got: ${hits.map { it.uri }}")
    }

    @Test
    fun `cancelling a copy mid-transfer leaks no uncaught VfsError Cancelled`(@TempDir tempDir: Path) = runTest {
        // The copy() flow runs its GIO call on a coroutine. Cancelling the
        // consumer mid-transfer used to let the producer's CancellationException
        // be translated into VfsError.Cancelled — which is not a
        // CancellationException, so coroutine machinery could not swallow it and
        // it escaped to an uncaught handler. translateError now rethrows it.
        val src = File(tempDir.toFile(), "big.bin")
        java.io.RandomAccessFile(src, "rw").use { it.setLength(48L * 1024 * 1024) }
        val root = "file://${tempDir.toAbsolutePath()}"

        val escaped = java.util.concurrent.CopyOnWriteArrayList<Throwable>()
        val handler = Thread.currentThread().uncaughtExceptionHandler
        Thread.currentThread().setUncaughtExceptionHandler { _, e -> escaped.add(e) }

        val job = launch(kotlinx.coroutines.Dispatchers.IO) {
            try {
                backend.copy(
                    FileJob(opType = "copy", source = "$root/big.bin", dest = "$root/big-copy.bin", overwrite = true)
                ).collect { /* progress */ }
            } catch (e: Throwable) {
                escaped.add(e)
            }
        }
        delay(400)
        job.cancelAndJoin()
        delay(2000) // let any leaked producer finish and escape
        Thread.currentThread().setUncaughtExceptionHandler(handler)

        val leaked = escaped.filter { it !is kotlinx.coroutines.CancellationException }
        println("COPY_CANCEL escaped=[${leaked.joinToString { "${it::class.simpleName}: ${it.message}" }}]")
        assertTrue(
            leaked.none { it is VfsError.Cancelled },
            "VfsError.Cancelled escaped the cancelled producer: ${leaked.filter { it is VfsError.Cancelled }}"
        )
    }
}
