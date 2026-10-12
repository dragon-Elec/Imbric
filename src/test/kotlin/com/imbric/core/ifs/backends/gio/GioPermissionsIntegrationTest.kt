@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends.gio

import com.imbric.core.ifs.backends.gio.support.GioTypeMappers
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermission
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.Test

/**
 * Permission ground-truth tests.
 *
 * isWritable must come from GIO's `access::can-write` (full ACL/group/mount
 * semantics). The old owner-bit fast path lied whenever the owner bits and
 * effective access disagreed — POSIX ACL grants being the reproducible case.
 */
@Tag("integration")
class GioPermissionsIntegrationTest {

    private val backend = GioBackend()

    @Test
    fun `chmod-000 own file is not writable`(@TempDir tempDir: Path) = runTest {
        val file = File(tempDir.toFile(), "locked.txt")
        file.writeText("content")
        // mode 000 is a PRESENT unix::mode value (not an
        // absent attribute) whose owner bits all deny
        // write. The unixMode > 0 guard treats 0 as
        // "absent" — conflating present-zero with absent —
        // which routes this row to the access::can-write
        // query; the answer is false for a non-root owner.
        // (A read-only mount is the same shape with mode
        // 0644: owner bits allow, access::can-write denies.)
        Files.setPosixFilePermissions(file.toPath(), emptySet())
        try {
            val info = backend.getMetadata("file://${file.absolutePath}").getOrThrow()
            assertFalse(info.isWritable, "chmod-000 file must report isWritable=false")
        } finally {
            // Restore write permission so @TempDir cleanup can delete the file.
            file.setWritable(true, false)
        }
    }

    @Test
    fun `group grant beats owner-bit denial`(@TempDir tempDir: Path) = runTest {
        val file = File(tempDir.toFile(), "acl.txt")
        file.writeText("content")
        // Fixture: a file owned by another user whose owner bits
        // deny write (r--), plus a named-user ACL entry granting
        // the current user rw-. For this non-owner row the owner
        // bits deny while access::can-write allows — isWritable
        // must report the GIO ground truth, never the owner bits.
        //
        // Requires chown (a privileged environment): the file must
        // not be owned by the current user, because for the owner
        // the owner entry always governs (group/other/named-user
        // entries cannot grant the owner write). Skips when chown
        // is unavailable.
        Files.setPosixFilePermissions(
            file.toPath(), setOf(PosixFilePermission.OWNER_READ)
        )
        val chown = ProcessBuilder("chown", "nobody", file.absolutePath)
            .redirectErrorStream(true)
            .start()
        val chownExit = chown.waitFor()
        assumeTrue(chownExit == 0, "chown is unavailable — group-owned fixture needs a privileged environment")
        val currentUser = System.getProperty("user.name")
        val setfacl = ProcessBuilder("setfacl", "-m", "u:$currentUser:rw-", file.absolutePath)
            .redirectErrorStream(true)
            .start()
        assumeTrue(setfacl.waitFor() == 0, "setfacl is unsupported on this filesystem")
        val info = backend.getMetadata("file://${file.absolutePath}").getOrThrow()
        assertTrue(info.isWritable, "ACL-granted write must be visible via access::can-write")
    }

    @Test
    fun readOnlyMountShape() = runTest {
        // Priv-free stub of a read-only mount: the file
        // is owned by the current user with owner write
        // bits set (unix::mode 0644 = 420 decimal), but
        // the filesystem denies writes — GIO reports
        // access::can-write=false. The old owner-bit fast
        // path derived isWritable from the mode (true);
        // the ground truth is the access check (false).
        val gioInfo = org.gnome.gio.FileInfo()
        gioInfo.setName("stub.txt")
        gioInfo.setFileType(org.gnome.gio.FileType.REGULAR)
        gioInfo.setAttributeUint32("unix::mode", 420)
        gioInfo.setAttributeString("owner::user", System.getProperty("user.name"))
        gioInfo.setAttributeBoolean("access::can-write", false)
        val info = GioTypeMappers.toImbricFileInfo(
            uri = "file:///stub.txt", path = "/stub.txt", gioInfo = gioInfo
        )
        assertFalse(info.isWritable)
        assertTrue(info.isReadable)
    }
}
