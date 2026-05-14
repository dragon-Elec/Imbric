@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class, kotlinx.coroutines.ExperimentalCoroutinesApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.XferArbiter
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class UndoManagerTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var transactionManager: TransactionManager
    private lateinit var undoManager: UndoManager

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
    }

    private fun kotlinx.coroutines.test.TestScope.initManagers() {
        transactionManager = TransactionManager(BackendRegistry, XferArbiter, this)
        undoManager = UndoManager(BackendRegistry, transactionManager, this)
        
        // Connect them
        undoManager.attach()
    }

    @Test
    fun testUndoCopy() = runTest {
        initManagers()
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://dest", "file1.txt") // Simulate already copied

        val tx = Transaction(status = TransactionStatus.COMPLETED, description = "Copy file1.txt", isReversible = true)
        tx.addOperation(TransactionOperation(
            jobId = Uuid.random(),
            opType = "copy",
            src = "memory://src/file1.txt",
            dest = "memory://dest/file1.txt",
            status = TransactionStatus.COMPLETED,
            inversePayload = mapOf("action" to "undo_copy", "target" to "memory://dest/file1.txt")
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://dest/file1.txt"))
        assertTrue(undoManager.canUndo())
        
        val undoStarted = launch {
            undoManager.undo()
        }
        
        // Wait for all coroutines to finish
        advanceUntilIdle()
        
        assertFalse(backend.exists("memory://dest/file1.txt")) // Should be trashed
        assertTrue(undoManager.canRedo())
    }

    @Test
    fun testUndoRedoMove() = runTest {
        initManagers()
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://dest", "file2.txt") // Simulate already moved

        val tx = Transaction(status = TransactionStatus.COMPLETED, description = "Move file2.txt", isReversible = true)
        tx.addOperation(TransactionOperation(
            jobId = Uuid.random(),
            opType = "move",
            src = "memory://src/file2.txt",
            dest = "memory://dest/file2.txt",
            status = TransactionStatus.COMPLETED,
            inversePayload = mapOf("action" to "undo_move", "target" to "memory://dest/file2.txt", "dest" to "memory://src/file2.txt")
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://dest/file2.txt"))
        assertFalse(backend.exists("memory://src/file2.txt"))
        
        // UNDO
        undoManager.undo()
        advanceUntilIdle()
        
        // Move undone: should be back at src
        assertTrue(backend.exists("memory://src/file2.txt"))
        assertFalse(backend.exists("memory://dest/file2.txt"))
        
        // REDO
        undoManager.redo()
        advanceUntilIdle()
        
        // Move redone: should be back at dest
        assertFalse(backend.exists("memory://src/file2.txt"))
        assertTrue(backend.exists("memory://dest/file2.txt"))
    }
}
