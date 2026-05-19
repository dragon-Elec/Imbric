@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlinx.datetime.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNull
import kotlin.test.assertNotNull

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
        
        assertEquals("value", info.attributes["key"])
        attrs["key"] = "changed"
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

    // --- New fields tests (Phase 1A) ---
    
    @Test
    fun testNewFieldsDefaults() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain"
        )
        
        // New fields should have sensible defaults
        assertNull(info.trashTime, "trashTime should default to null")
        assertNull(info.recency, "recency should default to null")
        assertFalse(info.isStarred, "isStarred should default to false")
        assertNull(info.activationUri, "activationUri should default to null")
    }

    @Test
    fun testNewFieldsConstruction() {
        val trashTime = Instant.fromEpochSeconds(1700000000)
        val recency = Instant.fromEpochSeconds(1700001000)
        
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain",
            trashTime = trashTime,
            recency = recency,
            isStarred = true,
            activationUri = "file:///usr/bin/app"
        )
        
        assertEquals(trashTime, info.trashTime)
        assertEquals(recency, info.recency)
        assertTrue(info.isStarred)
        assertEquals("file:///usr/bin/app", info.activationUri)
    }

    // --- Computed properties tests (Phase 1A) ---
    
    @Test
    fun testIsArchiveComputation() {
        // Should be archive
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/zip").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-tar").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-7z-compressed").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-rar-compressed").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/gzip").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-bzip2").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-xz").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-compressed-tar").isArchive)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/vnd.android.apk+zip").isArchive, "Should detect +zip suffix")
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-something+rar").isArchive, "Should detect +rar suffix")
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-something+7z").isArchive, "Should detect +7z suffix")
        
        // Should NOT be archive
        assertFalse(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="text/plain").isArchive)
        assertFalse(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="image/png").isArchive)
        assertFalse(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=true, mimeType="application/zip").isArchive, "Directories should not be archive")
    }

    @Test
    fun testIsLaunchableComputation() {
        // Should be launchable
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-desktop").isLaunchable)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="application/x-executable").isLaunchable)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="text/plain", isExecutable=true).isLaunchable)
        assertTrue(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="text/plain", activationUri="file:///usr/bin/app").isLaunchable)
        
        // Should NOT be launchable
        assertFalse(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=false, mimeType="text/plain").isLaunchable)
        assertFalse(FileInfo(path="/a", uri="file:///a", name="a", isDirectory=true, mimeType="application/x-executable").isLaunchable, "Directories should not be launchable")
    }

    // --- Sort comparators tests ---
    
    @Test
    fun testSortByTrashTime() {
        val older = Instant.fromEpochSeconds(1000000000)
        val newer = Instant.fromEpochSeconds(1700000000)
        
        val files = listOf(
            FileInfo(path="/a", uri="file:///a", name="a.txt", isDirectory=false, mimeType="text/plain", trashTime=newer),
            FileInfo(path="/b", uri="file:///b", name="b.txt", isDirectory=false, mimeType="text/plain", trashTime=older),
            FileInfo(path="/d", uri="file:///d", name="d", isDirectory=true, mimeType="inode/directory", trashTime=older)
        )
        
        val sorted = files.sortedWith(FileInfo.SortByTrashTime)
        
        // Directories first, then by trash time descending (newest first)
        assertTrue(sorted[0].isDirectory, "Directory should be first")
        assertEquals(newer, sorted[1].trashTime, "Newer trash time should come first")
        assertEquals(older, sorted[2].trashTime, "Older trash time should come second")
    }

    @Test
    fun testSortByTrashTimeWithNulls() {
        val time = Instant.fromEpochSeconds(1000000000)
        
        val files = listOf(
            FileInfo(path="/a", uri="file:///a", name="a.txt", isDirectory=false, trashTime=null),
            FileInfo(path="/b", uri="file:///b", name="b.txt", isDirectory=false, trashTime=time),
            FileInfo(path="/c", uri="file:///c", name="c.txt", isDirectory=false, trashTime=null)
        )
        
        val sorted = files.sortedWith(FileInfo.SortByTrashTime)
        
        assertEquals(time, sorted[0].trashTime, "Non-null should come first")
        assertNull(sorted[1].trashTime, "Null should come last")
        assertNull(sorted[2].trashTime, "Null should come last")
    }

    @Test
    fun testSortByRecency() {
        val older = Instant.fromEpochSeconds(1000000000)
        val newer = Instant.fromEpochSeconds(1700000000)
        
        val files = listOf(
            FileInfo(path="/a", uri="file:///a", name="a.txt", isDirectory=false, mimeType="text/plain", recency=newer),
            FileInfo(path="/b", uri="file:///b", name="b.txt", isDirectory=false, mimeType="text/plain", recency=older),
            FileInfo(path="/d", uri="file:///d", name="d", isDirectory=true, mimeType="inode/directory", recency=older)
        )
        
        val sorted = files.sortedWith(FileInfo.SortByRecency)
        
        assertTrue(sorted[0].isDirectory, "Directory should be first")
        assertEquals(newer, sorted[1].recency, "Newer recency should come first")
        assertEquals(older, sorted[2].recency, "Older recency should come second")
    }

    @Test
    fun testSortByRecencyWithNulls() {
        val time = Instant.fromEpochSeconds(1000000000)
        
        val files = listOf(
            FileInfo(path="/a", uri="file:///a", name="a.txt", isDirectory=false, recency=null),
            FileInfo(path="/b", uri="file:///b", name="b.txt", isDirectory=false, recency=time),
            FileInfo(path="/c", uri="file:///c", name="c.txt", isDirectory=false, recency=null)
        )
        
        val sorted = files.sortedWith(FileInfo.SortByRecency)
        
        assertEquals(time, sorted[0].recency, "Non-null should come first")
        assertNull(sorted[1].recency, "Null should come last")
        assertNull(sorted[2].recency, "Null should come last")
    }

    // --- Metadata accessors tests (Phase 5) ---
    
    @Test
    fun testGetMetadata() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain",
            attributes = mapOf(
                "metadata::nautilus-tags-starred" to true,
                "metadata::custom-key" to "custom-value",
                "metadata::count" to 42,
                "standard::name" to "test.txt"
            )
        )
        
        assertEquals("custom-value", info.getMetadata("custom-key"))
        assertNull(info.getMetadata("nonexistent"))
        assertNull(info.getMetadata("standard::name"), "Should not find non-metadata keys")
    }

    @Test
    fun testGetMetadataInt() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain",
            attributes = mapOf(
                "metadata::count" to 42,
                "metadata::not-a-number" to "hello",
                "metadata::long-val" to 100L
            )
        )
        
        assertEquals(42, info.getMetadataInt("count"))
        assertNull(info.getMetadataInt("not-a-number"), "Should return null for non-numeric")
        assertEquals(100, info.getMetadataInt("long-val"), "Should convert Long to Int")
        assertNull(info.getMetadataInt("nonexistent"))
    }

    @Test
    fun testGetMetadataBool() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain",
            attributes = mapOf(
                "metadata::starred" to true,
                "metadata::not-bool" to "hello"
            )
        )
        
        assertEquals(true, info.getMetadataBool("starred"))
        assertNull(info.getMetadataBool("not-bool"))
        assertNull(info.getMetadataBool("nonexistent"))
    }

    @Test
    fun testGetMetadataKeys() {
        val info = FileInfo(
            path = "/tmp/test.txt",
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            isDirectory = false,
            mimeType = "text/plain",
            attributes = mapOf(
                "metadata::nautilus-tags-starred" to true,
                "metadata::custom-key" to "value",
                "standard::name" to "test.txt"
            )
        )
        
        val allMetadataKeys = info.getMetadataKeys()
        assertEquals(2, allMetadataKeys.size)
        assertTrue(allMetadataKeys.contains("nautilus-tags-starred"))
        assertTrue(allMetadataKeys.contains("custom-key"))
        
        val filteredKeys = info.getMetadataKeys("nautilus-")
        assertEquals(1, filteredKeys.size)
        assertTrue(filteredKeys.contains("nautilus-tags-starred"))
    }

    // --- Glob compilation tests ---

    @Test
    fun testCompileGlobSpecialCharacters() {
        // Pattern with parentheses should not throw PatternSyntaxException
        val regex = FileInfo.compileGlob("report(v2).*")
        assertTrue(regex.matches("report(v2).txt"))
        assertTrue(regex.matches("report(v2).pdf"))
        assertFalse(regex.matches("reportv2.txt"))
    }

    @Test
    fun testCompileGlobDotsAndBrackets() {
        val regex = FileInfo.compileGlob("file[1].txt")
        assertTrue(regex.matches("file[1].txt"))
        assertFalse(regex.matches("file1.txt"))
    }

    @Test
    fun testCompileGlobPlusAndDollar() {
        val regex = FileInfo.compileGlob("cost+$100.*")
        assertTrue(regex.matches("cost+$100.txt"))
        assertFalse(regex.matches("cost$100.txt"))
    }

    @Test
    fun testCompileGlobBraces() {
        val regex = FileInfo.compileGlob("backup{1}.zip")
        assertTrue(regex.matches("backup{1}.zip"))
        assertFalse(regex.matches("backup1.zip"))
        assertFalse(regex.matches("backup11.zip"))
    }

    @Test
    fun testCompileGlobWildcard() {
        val regex = FileInfo.compileGlob("*.jpg")
        assertTrue(regex.matches("photo.jpg"))
        assertTrue(regex.matches("PHOTO.JPG"))
        assertFalse(regex.matches("photo.png"))
    }
}
