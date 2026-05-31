@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.logic

import com.imbric.core.models.*
import kotlin.time.Instant
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertEquals

class XferArbiterTest {

    private val srcInfo = FileInfo(
        path = "/src/file.txt",
        uri = "file:///src/file.txt",
        name = "file.txt",
        displayName = "file.txt",
        isDirectory = false,
        isSymlink = false,
        symlinkTarget = null,
        size = 100,
        mimeType = "text/plain",
        modifiedTime = Instant.fromEpochSeconds(1000),
        accessedTime = null,
        createdTime = null,
        isHidden = false,
        isWritable = true,
        iconName = null,
        thumbnailPath = null
    )

    private val destInfo = srcInfo.copy(
        path = "/dest/file.txt",
        uri = "file:///dest/file.txt",
        size = 50,
        modifiedTime = Instant.fromEpochSeconds(500)
    )

    @Test
    fun testAlwaysOverwritePolicy() {
        val policy = SyncPolicy.AlwaysOverwrite
        val result = XferArbiter.decide(srcInfo, destInfo, policy)
        assertTrue(result is ConflictAction.Overwrite)
    }

    @Test
    fun testAlwaysSkipPolicy() {
        val policy = SyncPolicy.AlwaysSkip
        val result = XferArbiter.decide(srcInfo, destInfo, policy)
        assertTrue(result is ConflictAction.Skip)
    }

    @Test
    fun testAutoRenamePolicy() {
        val policy = SyncPolicy.AutoRename
        val result = XferArbiter.decide(srcInfo, destInfo, policy)
        assertTrue(result is ConflictAction.AutoRename)
    }

    @Test
    fun testModifiedOnlyPolicy() {
        val policy = SyncPolicy.ModifiedOnly
        // Different size -> modified -> Overwrite
        var result = XferArbiter.decide(srcInfo, destInfo, policy)
        assertTrue(result is ConflictAction.Overwrite)

        // Same size, same time -> not modified -> Skip
        val identicalDest = srcInfo.copy(path = "/dest/file.txt", uri = "file:///dest/file.txt")
        result = XferArbiter.decide(srcInfo, identicalDest, policy)
        assertTrue(result is ConflictAction.Skip)
    }

    @Test
    fun testCustomApplicationPolicy() {
        // App-layer policy that looks at a custom attribute
        class ChecksumSyncPolicy : BaseSyncPolicy() {
            override fun decide(src: FileInfo, dest: FileInfo): ConflictAction {
                val srcHash = src.attributes["checksum"]
                val destHash = dest.attributes["checksum"]
                return if (srcHash != null && srcHash == destHash) {
                    ConflictAction.Skip
                } else {
                    ConflictAction.Overwrite
                }
            }
        }
        
        val policy = ChecksumSyncPolicy()
        
        val srcWithHash = srcInfo.copy(attributes = mapOf("checksum" to "abc"))
        val destWithDifferentHash = destInfo.copy(attributes = mapOf("checksum" to "def"))
        val destWithSameHash = destInfo.copy(attributes = mapOf("checksum" to "abc"))
        
        assertEquals(ConflictAction.Overwrite, XferArbiter.decide(srcWithHash, destWithDifferentHash, policy))
        assertEquals(ConflictAction.Skip, XferArbiter.decide(srcWithHash, destWithSameHash, policy))
    }

    @Test
    fun testGenerateNewName() {
        assertEquals("photo (1).jpg", XferArbiter.generateNewName("photo.jpg"))
        assertEquals("photo (2).jpg", XferArbiter.generateNewName("photo (1).jpg"))
        assertEquals("photo (10).jpg", XferArbiter.generateNewName("photo (9).jpg"))
        assertEquals("README (1)", XferArbiter.generateNewName("README"))
        assertEquals("archive.tar (1).gz", XferArbiter.generateNewName("archive.tar.gz"))
        assertEquals("(1) (1).txt", XferArbiter.generateNewName("(1).txt"))
        assertEquals("file with space (1).txt", XferArbiter.generateNewName("file with space.txt"))
    }
}
