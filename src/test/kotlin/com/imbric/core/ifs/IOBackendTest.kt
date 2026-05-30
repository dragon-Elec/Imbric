@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs

import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNull
import kotlin.test.assertNotNull

class IOBackendTest {

    private lateinit var backend: InMemoryBackend

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
    }

    @Test
    fun testCreateAndListFiles() = runTest {
        backend.createFolder("memory://", "testDir")
        backend.createFile("memory://testDir", "file1.txt")
        backend.createFile("memory://testDir", "file2.txt")

        val children = backend.list("memory://testDir")
        assertEquals(2, children.size)
        assertTrue(children.any { it.name == "file1.txt" })
        assertTrue(children.any { it.name == "file2.txt" })
    }

    @Test
    fun testExistsAndMetadata() = runTest {
        backend.createFile("memory://", "testFile.txt")

        assertTrue(backend.exists("memory://testFile.txt"))
        assertFalse(backend.exists("memory://missing.txt"))

        val metadata = backend.getMetadata("memory://testFile.txt")
        assertTrue(metadata.isSuccess)
        assertEquals("testFile.txt", metadata.getOrNull()?.name)

        val missing = backend.getMetadata("memory://missing.txt")
        assertTrue(missing.isFailure)
    }

    @Test
    fun testRename() = runTest {
        backend.createFile("memory://", "oldName.txt")
        val result = backend.rename("memory://oldName.txt", "newName.txt")

        assertTrue(result.isSuccess)
        assertEquals("memory://newName.txt", result.getOrNull())
        assertTrue(backend.exists("memory://newName.txt"))
        assertFalse(backend.exists("memory://oldName.txt"))
    }

    @Test
    fun testDelete() = runTest {
        backend.createFile("memory://", "toBeDeleted.txt")
        assertTrue(backend.exists("memory://toBeDeleted.txt"))

        val job = FileJob(opType = "delete", source = "memory://toBeDeleted.txt")
        val result = backend.delete(job)

        assertTrue(result.isSuccess)
        assertFalse(backend.exists("memory://toBeDeleted.txt"))
    }

    // --- deepCount tests ---
    
    @Test
    fun testDeepCountEmptyDirectory() = runTest {
        backend.createFolder("memory://", "emptyDir")
        
        val results = backend.deepCount("memory://emptyDir").toList()
        
        // Default implementation only emits final result for empty dirs
        assertEquals(1, results.size, "Should emit final result only")
        assertTrue(results.last().isComplete, "Last result should be complete")
        assertEquals(0, results.last().files)
        assertEquals(0, results.last().directories)
        assertEquals(0L, results.last().totalSize)
    }

    @Test
    fun testDeepCountSingleLevel() = runTest {
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "file1.txt")
        backend.createFile("memory://dir", "file2.txt")
        
        val results = backend.deepCount("memory://dir").toList()
        val final = results.last()
        
        assertTrue(final.isComplete)
        assertEquals(2, final.files)
        assertEquals(0, final.directories)
    }

    @Test
    fun testDeepCountNestedDirectories() = runTest {
        backend.createFolder("memory://", "root")
        backend.createFolder("memory://root", "sub1")
        backend.createFolder("memory://root/sub1", "sub2")
        backend.createFile("memory://root", "file1.txt")
        backend.createFile("memory://root/sub1", "file2.txt")
        backend.createFile("memory://root/sub1/sub2", "file3.txt")
        
        val results = backend.deepCount("memory://root").toList()
        val final = results.last()
        
        assertTrue(final.isComplete)
        assertEquals(3, final.files)
        assertEquals(2, final.directories, "Should count sub1 and sub2")
    }

    @Test
    fun testDeepCountMaxDepth() = runTest {
        backend.createFolder("memory://", "root")
        backend.createFolder("memory://root", "level1")
        backend.createFolder("memory://root/level1", "level2")
        backend.createFile("memory://root", "file1.txt")
        backend.createFile("memory://root/level1", "file2.txt")
        backend.createFile("memory://root/level1/level2", "file3.txt")
        
        // Count with maxDepth=1: processes depth 0 and depth 1
        // depth 0: file1.txt + level1 directory
        // depth 1: file2.txt + level2 directory (but level2 is not recursed into)
        val results = backend.deepCount("memory://root", maxDepth = 1).toList()
        val final = results.last()
        
        assertTrue(final.isComplete)
        assertEquals(2, final.files, "Should count file1.txt and file2.txt")
        assertEquals(2, final.directories, "Should count level1 and level2")
    }

    // --- getThumbnailPath tests ---
    
    @Test
    fun testGetThumbnailPathNotRegistered() = runTest {
        backend.createFile("memory://", "file.txt")
        
        val path = backend.getThumbnailPath("memory://file.txt")
        assertNull(path, "Should return null when no thumbnail registered")
    }

    @Test
    fun testGetThumbnailPathRegistered() = runTest {
        backend.createFile("memory://", "file.txt")
        backend.registerThumbnail("memory://file.txt", "/tmp/thumb.png")
        
        val path = backend.getThumbnailPath("memory://file.txt")
        assertEquals("/tmp/thumb.png", path)
    }

    // --- generateThumbnail tests ---
    
    @Test
    fun testGenerateThumbnailSuccess() = runTest {
        backend.createFile("memory://", "file.txt")
        
        val result = backend.generateThumbnail("memory://file.txt")
        assertTrue(result.isSuccess)
        assertNotNull(result.getOrNull())
        assertTrue(result.getOrNull()!!.contains("thumbnails"))
    }

    @Test
    fun testGenerateThumbnailFailure() = runTest {
        backend.createFile("memory://", "file.txt")
        backend.markThumbnailFailed("memory://file.txt")
        
        val result = backend.generateThumbnail("memory://file.txt")
        assertTrue(result.isFailure)
    }

    @Test
    fun testGenerateThumbnailRegistersPath() = runTest {
        backend.createFile("memory://", "file.txt")
        
        // Before generation
        assertNull(backend.getThumbnailPath("memory://file.txt"))
        
        // Generate
        val result = backend.generateThumbnail("memory://file.txt")
        assertTrue(result.isSuccess, "generateThumbnail should succeed")
        
        // After generation
        val path = backend.getThumbnailPath("memory://file.txt")
        assertNotNull(path, "generateThumbnail should register the path")
    }

    @Test
    fun testDeepCountWithFailingSubdirectory() = runTest {
        backend.createFolder("memory://", "root")
        backend.createFile("memory://root", "file1.txt")
        backend.createFolder("memory://root", "failDir")
        backend.createFile("memory://root", "file2.txt")
        
        // Inject failure for failDir
        backend.failingUris.add("memory://root/failDir")
        
        val results = backend.deepCount("memory://root").toList()
        val final = results.last()
        
        assertTrue(final.isComplete)
        // Should have counted file1 and file2, and failDir as a directory, 
        // but skipped contents of failDir
        assertEquals(2, final.files)
        assertEquals(1, final.directories)
    }
}
