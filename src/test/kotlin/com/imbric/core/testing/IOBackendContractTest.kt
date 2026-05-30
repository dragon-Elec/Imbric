package com.imbric.core.testing

import com.imbric.core.ifs.IOBackend
import com.imbric.core.models.FileJob
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

@OptIn(ExperimentalUuidApi::class)
abstract class IOBackendContractTest {
    protected abstract fun createBackend(): IOBackend
    protected abstract fun getTestRootUri(): String
    protected abstract fun setupTestEnvironment()
    protected abstract fun teardownTestEnvironment()

    private lateinit var backend: IOBackend
    private lateinit var rootUri: String

    @BeforeEach
    fun setup() {
        setupTestEnvironment()
        backend = createBackend()
        rootUri = getTestRootUri()
    }

    @AfterEach
    fun teardown() {
        teardownTestEnvironment()
    }

    @Test
    fun testCreateAndList() = runTest {
        com.imbric.core.ifs.backends.TestUtils.withGlibPump {
            val folderUri = backend.createFolder(rootUri, "test_folder").getOrThrow()
            val fileUri = backend.createFile(folderUri, "test_file.txt").getOrThrow()

            assertTrue(backend.exists(folderUri))
            assertTrue(backend.exists(fileUri))

        val children = backend.list(folderUri)
        assertEquals(1, children.size)
        assertEquals("test_file.txt", children[0].name)
        assertEquals(fileUri, children[0].uri)
        }
    }

    @Test
    fun testRename() = runTest {
        com.imbric.core.ifs.backends.TestUtils.withGlibPump {
            val folderUri = backend.createFolder(rootUri, "rename_folder").getOrThrow()
            val fileUri = backend.createFile(folderUri, "old_name.txt").getOrThrow()

            val newUri = backend.rename(fileUri, "new_name.txt").getOrThrow()
            
            assertFalse(backend.exists(fileUri))
            assertTrue(backend.exists(newUri))
            
            val info = backend.getMetadata(newUri).getOrThrow()
            assertEquals("new_name.txt", info.name)
        }
    }

    @Test
    fun testDelete() = runTest {
        com.imbric.core.ifs.backends.TestUtils.withGlibPump {
            val folderUri = backend.createFolder(rootUri, "delete_folder").getOrThrow()
            val fileUri = backend.createFile(folderUri, "to_delete.txt").getOrThrow()

            val job = FileJob(id = Uuid.random(), opType = "delete", source = fileUri)
            backend.delete(job).getOrThrow()

            assertFalse(backend.exists(fileUri))
        }
    }
}