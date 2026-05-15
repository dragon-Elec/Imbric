@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.logic.*
import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.test.runTest
import kotlin.test.*
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

class HardeningIntegrationTest {
    
    private lateinit var backend: JITSimulatingBackend
    private lateinit var registry: BackendRegistry
    private lateinit var manager: TransactionManager
    private lateinit var orchestrator: TransferOrchestrator

    @BeforeTest
    fun setup() {
        backend = JITSimulatingBackend()
        BackendRegistry.registerIo("memory", backend)
        val dispatcher = TransactionDispatcher(BackendRegistry)
        manager = TransactionManager(BackendRegistry, XferArbiter, dispatcher)
        orchestrator = TransferOrchestrator(BackendRegistry, manager)
    }

    @Test
    fun `test JIT fallback when file appears after planning`() = runTest {
        val srcDir = "memory:///src"
        val destDir = "memory:///dest"
        val srcFile = "$srcDir/file.txt"
        val destFile = "$destDir/file.txt"
        
        backend.createFolder("memory:///", "src")
        backend.createFolder("memory:///", "dest")
        backend.createFile(srcDir, "file.txt")
        // dest/file.txt does NOT exist during setup
        
        var conflictCalled = false
        
        val flow = orchestrator.planAndExecute(
            sources = listOf(srcFile),
            destDir = destDir,
            onManualConflict = { context ->
                conflictCalled = true
                ConflictResponse(ConflictAction.Overwrite)
            }
        )

        val results = mutableListOf<TransactionEvent>()
        backend.injectExistsError = true 
        
        flow.collect { results.add(it) }
        
        assertTrue(backend.injectExistsErrorWasTriggered, "JIT Conflict should have been triggered")
        assertTrue(conflictCalled, "Manual conflict resolver should have been called")
        assertTrue(backend.exists(destFile), "File should have been copied eventually")
        val finalStatus = (results.last() as TransactionEvent.Finished).status
        assertEquals(TransactionStatus.COMPLETED, finalStatus)
    }

    private class JITSimulatingBackend : InMemoryBackend("memory") {
        var injectExistsError = false
        var injectExistsErrorWasTriggered = false

        override suspend fun copy(job: FileJob): Flow<TransferProgress> = flow {
            if (injectExistsError && !job.overwrite) {
                // Simulate race condition: file appeared
                fs[job.dest.removeSuffix("/")] = FileInfo(
                    path = job.dest, uri = job.dest, name = "dest.txt", displayName = "dest.txt",
                    isDirectory = false, size = 10, modifiedTime = null, isHidden = false, 
                    isWritable = true, iconName = "text-x-generic", mimeType = "text/plain"
                )
                injectExistsError = false // Only do it once
                injectExistsErrorWasTriggered = true
                throw VfsConflictException(1, "File exists")
            }
            super.copy(job).collect { emit(it) }
        }
    }
}
