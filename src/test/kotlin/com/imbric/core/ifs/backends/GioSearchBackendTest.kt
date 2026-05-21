package com.imbric.core.ifs.backends

import com.imbric.core.ifs.BackendCapabilities
import com.imbric.core.ifs.FileAction
import com.imbric.core.ifs.IOBackend
import com.imbric.core.ifs.LatencyProfile
import com.imbric.core.ifs.Locality
import com.imbric.core.models.FileInfo
import com.imbric.core.models.FileJob
import com.imbric.core.models.TransferProgress
import com.imbric.core.models.VfsQuery
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.time.Instant

class GioSearchBackendTest {

    class MockFallbackBackend(private val mockResults: List<FileInfo>) : IOBackend {
        override val scheme: String = "mock"
        override val displayName: String = "Mock Backend"

        var searchCalled = false
            private set

        override suspend fun canPerform(action: FileAction, uri: String): Boolean = true
        override fun list(uri: String): Flow<FileInfo> = flowOf()
        override suspend fun getMetadata(uri: String): Result<FileInfo> = Result.failure(Exception("Not implemented"))
        override fun exists(uri: String): Boolean = false
        override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> = Result.failure(Exception("Not implemented"))
        override suspend fun copy(job: FileJob): Flow<TransferProgress> = flowOf()
        override suspend fun move(job: FileJob): Flow<TransferProgress> = flowOf()
        override suspend fun trash(job: FileJob, recoverTrashUri: Boolean): Result<String> = Result.failure(Exception("Not implemented"))
        override suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String> = Result.failure(Exception("Not implemented"))
        override suspend fun delete(job: FileJob): Result<Unit> = Result.failure(Exception("Not implemented"))
        override suspend fun createFolder(parentUri: String, name: String): Result<String> = Result.failure(Exception("Not implemented"))
        override suspend fun createFile(parentUri: String, name: String): Result<String> = Result.failure(Exception("Not implemented"))
        override suspend fun rename(uri: String, newName: String): Result<String> = Result.failure(Exception("Not implemented"))

        override fun search(query: VfsQuery): Flow<FileInfo> {
            searchCalled = true
            return flowOf(*mockResults.toTypedArray())
        }
    }

    @Test
    fun testFallbackIsCalledWhenTrackerFails() = runTest {
        val mockFileInfo = FileInfo(
            uri = "file:///tmp/test.txt",
            name = "test.txt",
            size = 123L,
            isDirectory = false,
            mimeType = "text/plain"
        )
        val mockFallback = MockFallbackBackend(listOf(mockFileInfo))
        val searchBackend = object : GioSearchBackend(fallback = mockFallback) {
            override fun runTrackerSearch(query: VfsQuery): Flow<String> {
                throw Exception("Simulated Tracker failure")
            }
        }

        val query = VfsQuery(text = "test", rootUri = "file:///tmp")

        val results = searchBackend.search(query).toList()

        assertEquals(1, results.size)
        assertEquals("test.txt", results[0].name)
        assertEquals(true, mockFallback.searchCalled, "Fallback backend should have been called")
    }
}