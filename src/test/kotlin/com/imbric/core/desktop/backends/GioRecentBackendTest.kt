package com.imbric.core.desktop.backends

import com.imbric.core.ifs.backends.GioRecentBackend
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Test
import kotlin.test.assertTrue

class GioRecentBackendTest {
    @Test
    fun testListRecents() = runBlocking {
        val backend = GioRecentBackend()
        val items = backend.list("recent:///").toList()
        println("GioRecentBackend returned ${items.size} items")
        // Note: size might be 0 if the user has no recent items, but it shouldn't crash.
        assertTrue(items != null)
    }

    @Test
    fun testUnsupportedOperations() = runBlocking {
        val backend = GioRecentBackend()
        val dummyJob = com.imbric.core.models.FileJob(
            opType = "test",
            source = "recent:///dummy",
            dest = "recent:///dummy2"
        )

        val metadataResult = backend.getMetadata("recent:///dummy")
        assertTrue(metadataResult.isFailure)
        assertTrue(metadataResult.exceptionOrNull() is UnsupportedOperationException)

        val readHeaderResult = backend.readHeader("recent:///dummy", 1024)
        assertTrue(readHeaderResult.isFailure)
        assertTrue(readHeaderResult.exceptionOrNull() is UnsupportedOperationException)

        val trashResult = backend.trash(dummyJob, false)
        assertTrue(trashResult.isFailure)
        assertTrue(trashResult.exceptionOrNull() is UnsupportedOperationException)

        val restoreResult = backend.restoreFromTrash("recent:///dummy", "recent:///dummy")
        assertTrue(restoreResult.isFailure)
        assertTrue(restoreResult.exceptionOrNull() is UnsupportedOperationException)

        val deleteResult = backend.delete(dummyJob)
        assertTrue(deleteResult.isFailure)
        assertTrue(deleteResult.exceptionOrNull() is UnsupportedOperationException)

        val createFolderResult = backend.createFolder("recent:///", "newFolder")
        assertTrue(createFolderResult.isFailure)
        assertTrue(createFolderResult.exceptionOrNull() is UnsupportedOperationException)

        val createFileResult = backend.createFile("recent:///", "newFile")
        assertTrue(createFileResult.isFailure)
        assertTrue(createFileResult.exceptionOrNull() is UnsupportedOperationException)

        val renameResult = backend.rename("recent:///dummy", "newName")
        assertTrue(renameResult.isFailure)
        assertTrue(renameResult.exceptionOrNull() is UnsupportedOperationException)

        // empty flows for copy and move
        assertTrue(backend.copy(dummyJob).toList().isEmpty())
        assertTrue(backend.move(dummyJob).toList().isEmpty())
    }
}