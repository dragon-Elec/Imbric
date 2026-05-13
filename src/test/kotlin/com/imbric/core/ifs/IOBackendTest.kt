@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs

import com.imbric.core.models.FileJob
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class IOBackendTest {

    private lateinit var backend: InMemoryBackend

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
    }

    @Test
    fun testCreateAndListFiles() = runTest {
        backend.createFolder("memory://", "testDir")
        backend.createFile("memory://testDir", "file1.txt")
        backend.createFile("memory://testDir", "file2.txt")

        val children = backend.list("memory://testDir").toList()
        assertEquals(2, children.size)
        assertTrue(children.any { it.name == "file1.txt" })
        assertTrue(children.any { it.name == "file2.txt" })
    }

    @Test
    fun testExistsAndMetadata() = runTest {
        backend.createFile("memory://", "testFile.txt")

        assertTrue(backend.exists("memory://testFile.txt"))
        assertFalse(backend.exists("memory://missing.txt"))

        val metadata = backend.getMetadata("memory://testFile.txt")
        assertTrue(metadata.isSuccess)
        assertEquals("testFile.txt", metadata.getOrNull()?.name)

        val missing = backend.getMetadata("memory://missing.txt")
        assertTrue(missing.isFailure)
    }

    @Test
    fun testRename() = runTest {
        backend.createFile("memory://", "oldName.txt")
        val result = backend.rename("memory://oldName.txt", "newName.txt")

        assertTrue(result.isSuccess)
        assertEquals("memory://newName.txt", result.getOrNull())
        assertTrue(backend.exists("memory://newName.txt"))
        assertFalse(backend.exists("memory://oldName.txt"))
    }

    @Test
    fun testDelete() = runTest {
        backend.createFile("memory://", "toBeDeleted.txt")
        assertTrue(backend.exists("memory://toBeDeleted.txt"))

        val job = FileJob(opType = "delete", source = "memory://toBeDeleted.txt")
        val result = backend.delete(job)

        assertTrue(result.isSuccess)
        assertFalse(backend.exists("memory://toBeDeleted.txt"))
    }
}
