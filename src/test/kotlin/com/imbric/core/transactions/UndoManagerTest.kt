@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class, kotlinx.coroutines.ExperimentalCoroutinesApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.XferArbiter
import com.imbric.core.models.UndoAction
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
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
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
        val dispatcher = TransactionDispatcher(BackendRegistry, this)
        transactionManager = TransactionManager(BackendRegistry, XferArbiter, dispatcher, this)
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
            undoAction = UndoAction.TransferUndo(
                undoLabel = "Copy",
                itemDescription = "file1.txt",
                destinations = listOf("memory://dest/file1.txt"),
                backendId = "memory"
            )
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://dest/file1.txt"))
        assertTrue(undoManager.canUndo())
        assertEquals("Undo Copy", undoManager.getUndoLabel())
        
        val undoStarted = launch {
            undoManager.undo()
        }
        
        // Wait for all coroutines to finish
        advanceUntilIdle()
        
        assertFalse(backend.exists("memory://dest/file1.txt")) // Should be trashed
        assertTrue(undoManager.canRedo())
        assertEquals("Redo Copy", undoManager.getRedoLabel())
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
            undoAction = UndoAction.TransferUndo(
                undoLabel = "Move",
                itemDescription = "file2.txt",
                destinations = listOf("memory://dest/file2.txt"),
                sources = listOf("memory://src/file2.txt"),
                srcDir = "memory://src",
                backendId = "memory"
            )
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://dest/file2.txt"))
        assertFalse(backend.exists("memory://src/file2.txt"))
        assertEquals("Undo Move", undoManager.getUndoLabel())
        
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

    @Test
    fun testUndoCreate() = runTest {
        initManagers()
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "newfile.txt") // Simulate already created

        val tx = Transaction(status = TransactionStatus.COMPLETED, description = "Create newfile.txt", isReversible = true)
        tx.addOperation(TransactionOperation(
            jobId = Uuid.random(),
            opType = "create",
            src = "memory://docs/newfile.txt",
            dest = "",
            status = TransactionStatus.COMPLETED,
            undoAction = UndoAction.CreateUndo(
                itemDescription = "newfile.txt",
                createdUri = "memory://docs/newfile.txt",
                backendId = "memory"
            )
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://docs/newfile.txt"))
        assertEquals("Undo Create", undoManager.getUndoLabel())
        
        // UNDO
        undoManager.undo()
        advanceUntilIdle()
        
        assertFalse(backend.exists("memory://docs/newfile.txt"))
    }

    @Test
    fun testUndoRename() = runTest {
        initManagers()
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "new_name.txt") // Simulate already renamed

        val tx = Transaction(status = TransactionStatus.COMPLETED, description = "Rename old_name.txt to new_name.txt", isReversible = true)
        tx.addOperation(TransactionOperation(
            jobId = Uuid.random(),
            opType = "rename",
            src = "memory://docs/old_name.txt",
            dest = "memory://docs/new_name.txt",
            status = TransactionStatus.COMPLETED,
            undoAction = UndoAction.RenameUndo(
                itemDescription = "old_name.txt",
                currentUri = "memory://docs/new_name.txt",
                originalUri = "memory://docs/old_name.txt",
                currentName = "new_name.txt",
                originalName = "old_name.txt",
                backendId = "memory"
            )
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(backend.exists("memory://docs/new_name.txt"))
        assertEquals("Undo Rename", undoManager.getUndoLabel())
        
        // UNDO
        undoManager.undo()
        advanceUntilIdle()
        
        assertFalse(backend.exists("memory://docs/new_name.txt"))
        assertTrue(backend.exists("memory://docs/old_name.txt"))
    }

    @Test
    fun testGetUndoLabelReturnsNullWhenEmpty() = runTest {
        initManagers()
        assertNull(undoManager.getUndoLabel())
        assertNull(undoManager.getRedoLabel())
    }

    @Test
    fun testUndoTrash() = runTest {
        initManagers()
        backend.createFolder("memory://", "docs")
        backend.createFile("memory://docs", "file.txt")
        // Simulate trash by moving to trash map
        backend.trashFile("memory://docs/file.txt")

        val tx = Transaction(status = TransactionStatus.COMPLETED, description = "Trash file.txt", isReversible = true)
        tx.addOperation(TransactionOperation(
            jobId = Uuid.random(),
            opType = "trash",
            src = "memory://docs/file.txt",
            dest = "",
            status = TransactionStatus.COMPLETED,
            undoAction = UndoAction.TrashUndo(
                itemDescription = "file.txt",
                trashedUris = listOf("memory://docs/file.txt"),
                originalUris = listOf("memory://docs/file.txt"),
                backendId = "memory"
            )
        ))

        undoManager.commitTransaction(tx)
        
        assertTrue(undoManager.canUndo())
        assertEquals("Undo Trash", undoManager.getUndoLabel())
        
        // UNDO — should restore from trash
        undoManager.undo()
        advanceUntilIdle()
        
        assertTrue(backend.exists("memory://docs/file.txt"))
    }
}
