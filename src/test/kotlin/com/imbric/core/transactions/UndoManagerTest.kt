@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.Transaction
import com.imbric.core.transactions.models.TransactionOperation
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.delay
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class UndoManagerTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var undoManager: UndoManager

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
        undoManager = UndoManager(BackendRegistry)
    }

    @Test
    fun testUndoCopy() = runTest {
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://dest", "file1.txt") // Simulate already copied

        val tx = Transaction(status = TransactionStatus.COMPLETED)
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
        
        var undoFinished = false
        undoManager.onOperationFinished = { _, _ -> undoFinished = true }
        undoManager.undo()
        
        val endTime = System.currentTimeMillis() + 2000
        while (!undoFinished && System.currentTimeMillis() < endTime) {
            delay(10)
        }
        
        assertFalse(backend.exists("memory://dest/file1.txt")) // Should be trashed
        assertTrue(undoManager.canRedo())
    }

    @Test
    fun testUndoRedoMove() = runTest {
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://dest", "file2.txt") // Simulate already moved

        val tx = Transaction(status = TransactionStatus.COMPLETED)
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
        
        var undoFinished = false
        var undoSuccess = false
        undoManager.onOperationFinished = { success, _ -> 
            undoFinished = true
            undoSuccess = success
        }
        undoManager.undo()
        
        var endTime = System.currentTimeMillis() + 2000
        while (!undoFinished && System.currentTimeMillis() < endTime) {
            delay(10)
        }
        println("Undo finished, success: $undoSuccess")
        
        // Move undone: should be back at src
        assertTrue(backend.exists("memory://src/file2.txt"))
        assertFalse(backend.exists("memory://dest/file2.txt"))
        
        undoFinished = false
        var redoSuccess = false
        undoManager.onOperationFinished = { success, _ -> 
            undoFinished = true
            redoSuccess = success
        }
        undoManager.redo()
        endTime = System.currentTimeMillis() + 2000
        while (!undoFinished && System.currentTimeMillis() < endTime) {
            delay(10)
        }
        println("Redo finished, success: $redoSuccess")
        
        // Move redone: should be back at dest
        assertFalse(backend.exists("memory://src/file2.txt"))
        assertTrue(backend.exists("memory://dest/file2.txt"))
    }
}
