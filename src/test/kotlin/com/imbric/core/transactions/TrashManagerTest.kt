@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.models.TrashItem
import com.imbric.core.testing.FakeTrashStateProvider
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
    private lateinit var fakeTrashState: FakeTrashStateProvider

    @BeforeEach
    fun setup() {
        BackendRegistry.clear()
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
        fakeTrashState = FakeTrashStateProvider()
        trashManager = TrashManager(BackendRegistry, trashState = fakeTrashState)
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
        assertTrue(trashResult.failed.isEmpty(), "Trash operation should succeed")
        assertEquals(1, trashResult.successful.size)
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
        
        val trashResult = trashManager.trashFiles(listOf("memory://docs/file1.txt", "memory://docs/file2.txt"))
        assertTrue(trashResult.failed.isEmpty(), "Trash operation should succeed, but failed: ${trashResult.failed}")
        assertEquals(2, trashResult.successful.size)
        
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
        
        // Initial state
        assertTrue(trashManager.isTrashEmpty(), "Trash should be empty initially")
        assertEquals(0, fakeTrashState.refreshCount)
        
        // Trash a file
        trashManager.trashFiles(listOf("memory://docs/file1.txt"))
        
        // Verify refresh was called
        assertEquals(1, fakeTrashState.refreshCount)
        
        // Manually update fake state (simulating what a real monitor would do after refresh)
        fakeTrashState.setEmpty(false)
        assertFalse(trashManager.isTrashEmpty(), "Trash should not be empty after trashing")
        
        // Empty trash
        trashManager.emptyTrash()
        assertEquals(2, fakeTrashState.refreshCount)
        
        fakeTrashState.setEmpty(true)
        assertTrue(trashManager.isTrashEmpty(), "Trash should be empty after emptying")
    }
}
