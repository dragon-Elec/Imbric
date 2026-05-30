@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import kotlin.test.*
import kotlin.uuid.ExperimentalUuidApi

class VfsQueryFilterTest {
    private val backend = InMemoryBackend()

    @BeforeTest
    fun setup() {
        // Create test files with different sizes and dates
        val now = kotlin.time.Clock.System.now()
        backend.fs["memory:///docs"] = FileInfo(
            name = "docs", path = "memory:///docs", uri = "memory:///docs",
            isDirectory = true, size = 0, mimeType = "inode/directory",
            modifiedTime = now, iconName = "folder"
        )
        backend.fs["memory:///docs/report.txt"] = FileInfo(
            name = "report.txt", path = "memory:///docs/report.txt", uri = "memory:///docs/report.txt",
            isDirectory = false, size = 5000, mimeType = "text/plain",
            modifiedTime = now, iconName = "text-x-generic"
        )
        backend.fs["memory:///docs/photo.jpg"] = FileInfo(
            name = "photo.jpg", path = "memory:///docs/photo.jpg", uri = "memory:///docs/photo.jpg",
            isDirectory = false, size = 2000000, mimeType = "image/jpeg",
            modifiedTime = now, iconName = "image-x-generic"
        )
        backend.fs["memory:///docs/big-video.mp4"] = FileInfo(
            name = "big-video.mp4", path = "memory:///docs/big-video.mp4", uri = "memory:///docs/big-video.mp4",
            isDirectory = false, size = 500000000, mimeType = "video/mp4",
            modifiedTime = now, iconName = "video-x-generic"
        )
    }

    @Test
    fun `test search with size filter`() = runTest {
        val query = VfsQuery(text = "", rootUri = "memory:///docs", minSize = 1000000)
        val results = backend.search(query).toList().flatten()
        assertEquals(2, results.size) // photo.jpg and big-video.mp4
        assertTrue(results.all { it.size >= 1000000 })
    }

    @Test
    fun `test search with max size filter`() = runTest {
        val query = VfsQuery(text = "", rootUri = "memory:///docs", maxSize = 10000)
        val results = backend.search(query).toList().flatten()
        assertEquals(1, results.size) // report.txt only
        assertEquals("report.txt", results[0].name)
    }

    @Test
    fun `test search with size range filter`() = runTest {
        val query = VfsQuery(text = "", rootUri = "memory:///docs", minSize = 1000, maxSize = 10000000)
        val results = backend.search(query).toList().flatten()
        assertEquals(2, results.size) // report.txt and photo.jpg
    }

    @Test
    fun `test search with mime filter`() = runTest {
        val query = VfsQuery(text = "", rootUri = "memory:///docs", mimeFilter = "image/")
        val results = backend.search(query).toList().flatten()
        assertEquals(1, results.size)
        assertEquals("photo.jpg", results[0].name)
    }
}
