@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.XferArbiter
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.delay
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

class TransactionManagerTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var tm: TransactionManager

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
        BackendRegistry.registerIo("memory", backend)
        val dispatcher = TransactionDispatcher(BackendRegistry)
        tm = TransactionManager(BackendRegistry, XferArbiter, dispatcher)
    }

    @Test
    fun testBatchTransfer_AllSucceed() = runTest {
        // Setup files
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://src", "file1.txt")
        backend.createFile("memory://src", "file2.txt")
        backend.createFile("memory://src", "file3.txt")

        var finishedStatus: TransactionStatus? = null
        tm.onTransactionFinished = { _, status -> finishedStatus = status }
        
        val tid = tm.startTransaction("Batch transfer")
        tm.addOperation(tid, "copy", "memory://src/file1.txt", "memory://dest/file1.txt")
        tm.addOperation(tid, "copy", "memory://src/file2.txt", "memory://dest/file2.txt")
        tm.addOperation(tid, "copy", "memory://src/file3.txt", "memory://dest/file3.txt")
        tm.commitTransaction(tid)
        
        // Wait for coroutines to finish
        val endTime = System.currentTimeMillis() + 2000
        while (finishedStatus == null && System.currentTimeMillis() < endTime) {
            delay(10)
        }

        assertEquals(TransactionStatus.COMPLETED, finishedStatus)
        assertTrue(backend.exists("memory://dest/file1.txt"))
        assertTrue(backend.exists("memory://dest/file2.txt"))
        assertTrue(backend.exists("memory://dest/file3.txt"))
    }

    @Test
    fun testBatchTransfer_PartialFailure() = runTest {
        // Setup files
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://src", "file1.txt")
        // Deliberately miss file2.txt to cause a failure

        val sources = listOf(
            "memory://src/file1.txt",
            "memory://src/file2.txt" // Does not exist
        )

        var finishedStatus: TransactionStatus? = null
        tm.onTransactionFinished = { _, status -> finishedStatus = status }

        val tid = tm.batchTransfer(sources, "memory://dest")
        
        val endTime = System.currentTimeMillis() + 2000
        while (finishedStatus == null && System.currentTimeMillis() < endTime) {
            delay(10)
        }

        assertEquals(TransactionStatus.PARTIAL, finishedStatus)
        assertTrue(backend.exists("memory://dest/file1.txt")) // Succeeded
        // file2 failed
    }

    @Test
    fun testTransactionProgressAggregates() = runTest {
        backend.createFolder("memory://", "src")
        backend.createFolder("memory://", "dest")
        backend.createFile("memory://src", "file1.txt")

        val sources = listOf("memory://src/file1.txt")

        var lastProgress = 0f
        tm.onTransactionProgress = { _, pct -> lastProgress = pct }
        var finishedStatus: TransactionStatus? = null
        tm.onTransactionFinished = { _, status -> finishedStatus = status }

        tm.batchTransfer(sources, "memory://dest")
        
        val endTime = System.currentTimeMillis() + 2000
        while (finishedStatus == null && System.currentTimeMillis() < endTime) {
            delay(10)
        }
        
        assertTrue(lastProgress > 0f)
        assertEquals(TransactionStatus.COMPLETED, finishedStatus)
        // Note: the progress implementation in Transaction might need checking if this fails
    }
}
