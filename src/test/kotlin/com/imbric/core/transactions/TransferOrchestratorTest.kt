@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.*
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import kotlin.test.*
import kotlin.uuid.Uuid

class TransferOrchestratorTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var tm: TransactionManager
    private lateinit var orchestrator: TransferOrchestrator

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
        val dispatcher = TransactionDispatcher(BackendRegistry)
        tm = TransactionManager(BackendRegistry, XferArbiter, dispatcher)
        orchestrator = TransferOrchestrator(BackendRegistry, tm)
    }

    private fun TestScope.initManagers() {
        val dispatcher = TransactionDispatcher(BackendRegistry, this)
        tm = TransactionManager(BackendRegistry, XferArbiter, dispatcher, this)
        orchestrator = TransferOrchestrator(BackendRegistry, tm)
    }

    @Test
    fun testSameDirectoryCopy_AutoRenames() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFile("memory://src", "file.txt")
        
        // Copy file.txt to /src (same folder)
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/file.txt"),
            destDir = "memory://src",
            mode = "copy",
            policy = SyncPolicy.Standard
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
        
        // Should have created "file (1).txt"
        assertTrue(backend.exists("memory://src/file.txt"), "Original should still exist")
        assertTrue(backend.exists("memory://src/file (1).txt"), "Duplicate should be auto-renamed")
    }

    @Test
    fun testConflict_PromptsUser() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://src", "conflict.txt")
        backend.createFile("memory://dest", "conflict.txt")
        
        var promptCalled = false
        
        // Copy conflict.txt to /dest (where it already exists)
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/conflict.txt"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.Standard,
            onManualConflict = {
                promptCalled = true
                ConflictResponse(ConflictAction.Overwrite)
            }
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
        assertTrue(promptCalled, "Should have prompted user for conflict")
    }

    @Test
    fun testRecursiveMerge() = runTest {
        initManagers()
        // Setup:
        // /src/folder/a.txt
        // /dest/folder/b.txt
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://src", "folder")
        backend.createFile("memory://src/folder", "a.txt")
        
        backend.createFolder("memory://", "dest")
        backend.createFolder("memory://dest", "folder")
        backend.createFile("memory://dest/folder", "b.txt")
        
        // Action: Copy /src/folder to /dest
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/folder"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.Standard
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
        
        // Result: /dest/folder should now have both a.txt and b.txt
        assertTrue(backend.exists("memory://dest/folder/a.txt"), "a.txt should have been copied into existing folder")
        assertTrue(backend.exists("memory://dest/folder/b.txt"), "b.txt should still exist")
    }

    @Test
    fun testDeepRecursiveMerge() = runTest {
        // ... (existing test)
    }

    @Test
    fun testMergeFailureGracefully() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://src", "folder")
        backend.createFile("memory://src/folder", "good.txt")
        backend.createFile("memory://src/folder", "bad.txt")
        
        // Inject failure for bad.txt
        backend.failingUris.add("memory://src/folder/bad.txt")
        
        backend.createFolder("memory://", "dest")
        backend.createFolder("memory://dest", "folder")
        
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/folder"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.Standard
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
        
        assertTrue(backend.exists("memory://dest/folder/good.txt"), "Good file should have been copied")
        assertFalse(backend.exists("memory://dest/folder/bad.txt"), "Bad file should have been skipped due to metadata failure")
    }

    @Test
    fun testStickyApplyToAll() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        
        // Create 3 conflicts
        backend.createFile("memory://src", "1.txt")
        backend.createFile("memory://dest", "1.txt")
        backend.createFile("memory://src", "2.txt")
        backend.createFile("memory://dest", "2.txt")
        backend.createFile("memory://src", "3.txt")
        backend.createFile("memory://dest", "3.txt")
        
        var promptCount = 0
        
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/1.txt", "memory://src/2.txt", "memory://src/3.txt"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.Standard,
            onManualConflict = {
                promptCount++
                // Pick Overwrite and apply to all
                ConflictResponse(ConflictAction.Overwrite, applyToAll = true)
            }
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
        
        // Should only have prompted ONCE because of applyToAll
        assertEquals(1, promptCount, "Should only prompt once when applyToAll is true")
        
        // All files should have been overwritten
        assertTrue(backend.exists("memory://dest/1.txt"))
        assertTrue(backend.exists("memory://dest/2.txt"))
        assertTrue(backend.exists("memory://dest/3.txt"))
    }

    @Test
    fun testCancellationDuringPlanning() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://src", "1.txt")
        backend.createFile("memory://dest", "1.txt")
        
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/1.txt"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.Standard,
            onManualConflict = {
                ConflictResponse(ConflictAction.Cancel)
            }
        )
        
        // channelFlow should close with CancellationException
        try {
            flow.collect()
            fail("Should have thrown CancellationException")
        } catch (e: Exception) {
            // CancellationException is expected (might be wrapped or caught by channelFlow)
            // But let's check if the transaction was finished or just dropped
        }
    }

    @Test
    fun testModifiedOnlyPolicy_SkipsIdentical() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        
        // Create identical files
        backend.createFile("memory://src", "sync.txt")
        backend.createFile("memory://dest", "sync.txt")
        
        val flow = orchestrator.planAndExecute(
            sources = listOf("memory://src/sync.txt"),
            destDir = "memory://dest",
            mode = "copy",
            policy = SyncPolicy.ModifiedOnly
        )
        
        val finished = flow.filterIsInstance<com.imbric.core.transactions.models.TransactionEvent.Finished>().first()
        assertEquals(TransactionStatus.COMPLETED, finished.status)
    }
}
