@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.models.TrashItem
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.BeforeEach
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.test.assertNotNull

class TrashManagerTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var trashManager: TrashManager

    @BeforeEach
    fun setup() {
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
        trashManager = TrashManager(BackendRegistry)
    }

    @Test
    fun testTrashAndRestore() = runTest {
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "file1.txt")
        backend.createFile("memory://docs", "file2.txt")
        
        println(backend.fs.keys)
        assertTrue(backend.exists("memory://docs/file1.txt"))
        
        // Trash one file
        val trashResult = trashManager.trashFiles(listOf("memory://docs/file1.txt"))
        println("Trash result: $trashResult")
        assertTrue(trashResult.isSuccess)
        assertFalse(backend.exists("memory://docs/file1.txt"), "File should not exist after trashing")
        
        // Check trash list
        val items = trashManager.listTrashItems()
        assertEquals(1, items.size)
        val trashItem = items.first()
        assertEquals("file1.txt", trashItem.name)
        assertEquals("memory://docs/file1.txt", trashItem.originalPath)
        
        // Restore
        val restoreResult = trashManager.restoreFromTrash(trashItem)
        println("Restore result: $restoreResult")
        assertTrue(restoreResult.isSuccess, "Restore should be successful")
        assertTrue(backend.exists("memory://docs/file1.txt"))
        
        // Empty trash
        val emptyItems = trashManager.listTrashItems()
        assertTrue(emptyItems.isEmpty())
    }

    @Test
    fun testEmptyTrash() = runTest {
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "file1.txt")
        backend.createFile("memory://docs", "file2.txt")
        
        trashManager.trashFiles(listOf("memory://docs/file1.txt", "memory://docs/file2.txt"))
        
        var items = trashManager.listTrashItems()
        assertEquals(2, items.size)
        
        val emptyResult = trashManager.emptyTrash()
        assertTrue(emptyResult.isSuccess)
        
        items = trashManager.listTrashItems()
        assertTrue(items.isEmpty())
    }

    @Test
    fun testTrashEmptyStateFlow() = runTest {
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "file1.txt")
        
        // Note: isTrashEmpty is backed by TrashMonitor which monitors real trash:///
        // via GIO, not InMemoryBackend. We can only verify listTrashItems behavior here.
        val initialItems = trashManager.listTrashItems()
        assertEquals(0, initialItems.size, "InMemoryBackend trash should be empty initially")
        
        trashManager.trashFiles(listOf("memory://docs/file1.txt"))
        val afterTrashItems = trashManager.listTrashItems()
        assertEquals(1, afterTrashItems.size, "Should have 1 item after trashing")
        
        trashManager.emptyTrash()
        val afterEmptyItems = trashManager.listTrashItems()
        assertTrue(afterEmptyItems.isEmpty(), "Trash should be empty after emptying")
    }
}
