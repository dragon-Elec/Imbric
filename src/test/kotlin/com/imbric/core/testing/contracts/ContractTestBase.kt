package com.imbric.core.testing.contracts

import com.imbric.core.models.FileJob
import com.imbric.core.testing.FakeFilesystem
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

/**
 * Base class for all behavioral contract tests.
 * Uses real coroutines — no TestScope, no advanceUntilIdle.
 *
 * To add a new contract:
 * 1. Create `MyContractTest.kt`
 * 2. Extend this class
 * 3. Write tests using `contractTest { ... }`
 */
@OptIn(ExperimentalUuidApi::class)
abstract class ContractTestBase {

    protected lateinit var fs: FakeFilesystem

    @BeforeEach
    fun setUp() {
        fs = FakeFilesystem()
    }

    @AfterEach
    fun tearDown() {
        fs.destroy()
    }

    /** Run a contract test — block is a regular function, suspend calls use runBlocking. */
    protected fun contractTest(block: ContractTestContext.() -> Unit) {
        ContractTestContext(fs).block()
    }

    protected class ContractTestContext(val fs: FakeFilesystem) {
        fun openDir(dirUri: String) = fs.openDir(dirUri)
        fun createFile(path: String) = fs.createFile(path)
        fun createFolder(path: String) = fs.createFolder(path)
        fun createFiles(vararg paths: String) = fs.createFiles(*paths)
        fun deleteFile(path: String) = fs.deleteFile(path)
        fun simulateCreated(path: String) = fs.simulateFileCreated(path)
        fun simulateDeleted(path: String) = fs.simulateFileDeleted(path)
        fun simulateModified(path: String) = fs.simulateFileModified(path)
        fun simulateRenamed(from: String, to: String) = fs.simulateFileRenamed(from, to)

        /** Wait for async events to propagate. */
        fun waitForEvents() { Thread.sleep(200) }

        /** Run a suspend block and return its result. */
        fun <T> runSuspend(block: suspend () -> T): T = runBlocking { block() }

        /** Helper to build a FileJob with less noise. */
        fun job(op: String, src: String, dest: String? = null) = FileJob(
            id = Uuid.random(), opType = op, source = src, dest = dest ?: ""
        )
    }
}
