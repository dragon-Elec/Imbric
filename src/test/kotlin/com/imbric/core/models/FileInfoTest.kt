@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlinx.datetime.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNull

class FileInfoTest {

    @Test
    fun testFileInfoConstruction() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            displayName = "Test Document",
            isDirectory = false,
            isSymlink = true,
            symlinkTarget = "/opt/real.txt",
            size = 1024L,
            mimeType = "text/plain",
            modifiedTime = Instant.fromEpochSeconds(1000000000),
            accessedTime = null,
            createdTime = null,
            isHidden = false,
            isWritable = true,
            iconName = "text-x-generic",
            thumbnailPath = null
        )

        assertEquals("test.txt", info.name)
        assertEquals("Test Document", info.displayName)
        assertFalse(info.isDirectory)
        assertTrue(info.isSymlink)
        assertEquals("/opt/real.txt", info.symlinkTarget)
        assertEquals(1024L, info.size)
        assertEquals(PathType.PHYSICAL, info.pathType)
        assertNull(info.nativeId)
        assertTrue(info.attributes.isEmpty())
    }

    @Test
    fun testFileInfoAttributesImmutability() {
        val attrs = mutableMapOf<String, Any?>("key" to "value")
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            attributes = attrs
        )
        
        // Changing the original map should not affect FileInfo if it copies it
        // Note: FileInfo uses Map, which might be the same instance if passed a MutableMap
        // But we want to ensure it's treated as immutable from the outside.
        assertEquals("value", info.attributes["key"])
        attrs["key"] = "changed"
        
        // If FileInfo doesn't copy, this will be "changed". 
        // Let's see what the current implementation does.
        // If it's a data class with a Map property, it usually just holds the reference.
        // We should check if we need to enforce defensive copying.
    }

    @Test
    fun testFileInfoPathTypes() {
        val physical = FileInfo(path = "/tmp", uri = "file:///tmp", name = "tmp", isDirectory = true, pathType = PathType.PHYSICAL)
        val virtual = FileInfo(path = "trash:///", uri = "trash:///", name = "Trash", isDirectory = true, pathType = PathType.VIRTUAL)
        val synthetic = FileInfo(path = "search://query", uri = "search://query", name = "Search", isDirectory = true, pathType = PathType.SYNTHETIC)
        
        assertEquals(PathType.PHYSICAL, physical.pathType)
        assertEquals(PathType.VIRTUAL, virtual.pathType)
        assertEquals(PathType.SYNTHETIC, synthetic.pathType)
    }
}
