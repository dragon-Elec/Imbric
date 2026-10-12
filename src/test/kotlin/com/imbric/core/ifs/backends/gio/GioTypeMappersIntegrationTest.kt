@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends.gio

import com.imbric.core.ifs.backends.gio.GioBackend
import com.imbric.core.ifs.backends.gio.support.GioTypeMappers
import com.imbric.core.ifs.directories.DirState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

@Tag("integration")
class GioTypeMappersIntegrationTest {

    private val backend = GioBackend()

    @Test
    fun testMetadataMappingToAttributes(@TempDir tempDir: Path) = runTest {
        val file = File(tempDir.toFile(), "mapping_test.txt")
        file.writeText("test content")
        val fileUri = "file://${file.absolutePath}"

        val result = backend.getMetadata(fileUri)
        assertTrue(result.isSuccess)
        
        val info = result.getOrThrow()
        
        // Check first-class fields
        assertEquals("mapping_test.txt", info.name)
        assertEquals(12L, info.size)
        
        // Check attributes bag (Secret Bag)
        val attrs = info.attributes
        assertTrue(attrs.isNotEmpty(), "Attributes bag should not be empty")
        
        // GIO attributes are prefixed with namespace (e.g. standard::size)
        // GioTypeMappers.toImbricFileInfo maps them as-is from getAttributeAsString

        assertNotNull(attrs["standard::size"], "standard::size should be in attributes")
        assertEquals(12L, attrs["standard::size"])

        assertNotNull(attrs["standard::display-name"], "standard::display-name should be in attributes")
        assertNotNull(attrs["standard::content-type"], "standard::content-type should be in attributes")

        // Check permissions in bag
        assertNotNull(attrs["access::can-read"])
        assertEquals(true, attrs["access::can-read"])
    }

    @Test
    fun `epoch-0 mtime is a real 1970 instant, absent mtime is null`() {
        // Presence, not value, decides null-vs-epoch-0: a queried
        // attribute the filesystem left unset is absent, while a
        // present zero is a real 1970 timestamp.
        val epochZero = org.gnome.gio.FileInfo()
        epochZero.setAttributeUint64("time::modified", 0L)
        val withEpochZero = GioTypeMappers.toImbricFileInfo(
            uri = "file:///epoch0", path = "/epoch0", gioInfo = epochZero
        )
        assertEquals(kotlin.time.Instant.fromEpochSeconds(0L), withEpochZero.modifiedTime)

        val absent = org.gnome.gio.FileInfo()
        val withAbsent = GioTypeMappers.toImbricFileInfo(
            uri = "file:///absent", path = "/absent", gioInfo = absent
        )
        assertNull(withAbsent.modifiedTime)
    }

    @Test
    fun `sub-second mtime round-trips through the mapper`() {
        val gioInfo = org.gnome.gio.FileInfo()
        gioInfo.setAttributeUint64("time::modified", 5L)
        gioInfo.setAttributeUint32("time::modified-nsec", 500_000_000)
        val info = GioTypeMappers.toImbricFileInfo(
            uri = "file:///nsec", path = "/nsec", gioInfo = gioInfo
        )
        assertEquals(kotlin.time.Instant.fromEpochSeconds(5L, 500_000_000), info.modifiedTime)
        assertEquals(5500L, info.modifiedTime?.toEpochMilliseconds())
    }

    @Test
    fun `same-second rewrite is visible in listing mtime`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val file = File(tempDir.toFile(), "rewrite.txt")
            file.writeText("a")
            val dirUri = "file://${tempDir.toAbsolutePath()}"
            val first = backend.list(dirUri).first { it.name == "rewrite.txt" }.modifiedTime
            // Same-second, same-size rewrite: sub-millisecond
            // mtime precision can tell the two listings apart —
            // whole-second truncation made DirState's dedup keep
            // the stale row.
            file.writeText("b")
            val second = backend.list(dirUri).first { it.name == "rewrite.txt" }.modifiedTime
            assertNotNull(first)
            assertNotNull(second)
            assertTrue(
                second > first,
                "same-second rewrite must advance mtime: first=$first second=$second"
            )
        }
    }

    @Test
    fun `mtime is millis-precision so it round-trips through the SoA`(@TempDir tempDir: Path) = runTest {
        TestUtils.withGlibPump {
            val file = File(tempDir.toFile(), "stable.txt")
            file.writeText("content")
            // ext4 mtimes carry nanoseconds; the SoA stores
            // epoch millis and reads rows back at millis
            // precision, and the dedup pass compares Instant
            // equality. A sub-millisecond value would never
            // equal its own cached read-back, so the choke
            // point truncates to millis — this is the exact
            // round-trip every unchanged row must survive.
            val info = backend.getMetadata("file://${file.absolutePath}").getOrThrow()
            val mtime = info.modifiedTime
            assertNotNull(mtime)
            assertEquals(
                kotlin.time.Instant.fromEpochMilliseconds(mtime.toEpochMilliseconds()),
                mtime,
                "mtime must be millis-aligned to round-trip the SoA"
            )
        }
    }

    @Test
    fun `unchanged refresh emits exactly once and warm onActive does not re-emit`(@TempDir tempDir: Path) = runBlocking {
        TestUtils.withGlibPump {
            File(tempDir.toFile(), "stable.txt").writeText("content")
            val dirUri = "file://${tempDir.toAbsolutePath()}"
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
            try {
                val dirState = DirState(dirUri, backend, scope, Dispatchers.Default)
                dirState.isLoading.first { !it }
                delay(100) // real time: the pump thread runs the GIO callbacks
                val afterLoad = dirState.revision.value

                // Unchanged refresh: exactly one emission
                // (the trailing rebuildComposite) — never a
                // second spurious one from rows the dedup
                // pass misjudged as changed.
                dirState.refresh()
                dirState.isLoading.first { !it }
                delay(200)
                assertEquals(
                    afterLoad + 1,
                    dirState.revision.value,
                    "refresh of an unchanged tree must emit exactly once"
                )

                // Warm revalidate of an unchanged tree: the
                // fingerprint compare (uri, size, millis mtime)
                // finds nothing different, so no composite is
                // published — the revision count stays stable.
                dirState.onActive()
                delay(500)
                assertEquals(
                    afterLoad + 1,
                    dirState.revision.value,
                    "warm onActive of an unchanged tree must not re-emit"
                )

                dirState.destroy()
            } finally {
                scope.cancel()
            }
        }
    }
}
