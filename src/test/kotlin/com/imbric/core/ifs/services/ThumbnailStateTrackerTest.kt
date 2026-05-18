@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.services

import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNull
import kotlin.test.assertNotNull

class ThumbnailStateTrackerTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var tracker: ThumbnailStateTracker

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend()
        tracker = ThumbnailStateTracker(backend)
    }

    @Test
    fun testCanThumbnailImages() {
        val imageInfo = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        assertTrue(tracker.canThumbnail(imageInfo))
    }

    @Test
    fun testCanThumbnailVideos() {
        val videoInfo = FileInfo(
            path = "/a.mp4", uri = "file:///a.mp4", name = "a.mp4",
            isDirectory = false, mimeType = "video/mp4", size = 1024
        )
        assertTrue(tracker.canThumbnail(videoInfo))
    }

    @Test
    fun testCanThumbnailPdf() {
        val pdfInfo = FileInfo(
            path = "/a.pdf", uri = "file:///a.pdf", name = "a.pdf",
            isDirectory = false, mimeType = "application/pdf", size = 1024
        )
        assertTrue(tracker.canThumbnail(pdfInfo))
    }

    @Test
    fun testCannotThumbnailDirectories() {
        val dirInfo = FileInfo(
            path = "/dir", uri = "file:///dir", name = "dir",
            isDirectory = true, mimeType = "inode/directory"
        )
        assertFalse(tracker.canThumbnail(dirInfo))
    }

    @Test
    fun testCannotThumbnailLargeFiles() {
        val largeInfo = FileInfo(
            path = "/large.png", uri = "file:///large.png", name = "large.png",
            isDirectory = false, mimeType = "image/png", size = 20 * 1024 * 1024 // 20MB
        )
        assertFalse(tracker.canThumbnail(largeInfo))
    }

    @Test
    fun testCannotThumbnailTextFiles() {
        val textInfo = FileInfo(
            path = "/a.txt", uri = "file:///a.txt", name = "a.txt",
            isDirectory = false, mimeType = "text/plain", size = 1024
        )
        assertFalse(tracker.canThumbnail(textInfo))
    }

    @Test
    fun testEnsureThumbnailFastPath() = runTest {
        val info = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        // Register a thumbnail in backend
        backend.registerThumbnail("file:///a.png", "/tmp/thumb_a.png")
        
        val path = tracker.ensureThumbnail(info)
        assertEquals("/tmp/thumb_a.png", path)
        
        // Should not have been in progress (fast path)
        assertFalse(tracker.isCurrentlyThumbnailing("file:///a.png"))
    }

    @Test
    fun testEnsureThumbnailGeneratesWhenMissing() = runTest {
        val info = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        // No thumbnail registered — should trigger generation
        val path = tracker.ensureThumbnail(info)
        assertNotNull(path, "Should generate thumbnail")
        assertTrue(path.contains("thumbnails"))
        
        // Should have completed (not in progress, not failed)
        assertFalse(tracker.isCurrentlyThumbnailing("file:///a.png"))
        assertFalse(tracker.hasFailed("file:///a.png"))
    }

    @Test
    fun testEnsureThumbnailTracksFailure() = runTest {
        val info = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        // Mark as failed in backend
        backend.markThumbnailFailed("file:///a.png")
        
        val path = tracker.ensureThumbnail(info)
        assertNull(path, "Should return null on failure")
        
        // Should be marked as failed
        assertTrue(tracker.hasFailed("file:///a.png"))
        assertFalse(tracker.isCurrentlyThumbnailing("file:///a.png"))
    }

    @Test
    fun testClearFailedState() = runTest {
        val info = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        backend.markThumbnailFailed("file:///a.png")
        tracker.ensureThumbnail(info)
        assertTrue(tracker.hasFailed("file:///a.png"))
        
        tracker.clearFailedState("file:///a.png")
        assertFalse(tracker.hasFailed("file:///a.png"))
    }

    @Test
    fun testClearAllState() = runTest {
        val info1 = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        val info2 = FileInfo(
            path = "/b.png", uri = "file:///b.png", name = "b.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        backend.markThumbnailFailed("file:///a.png")
        tracker.ensureThumbnail(info1)
        tracker.ensureThumbnail(info2)
        
        tracker.clearAllState()
        
        assertFalse(tracker.hasFailed("file:///a.png"))
        assertFalse(tracker.hasFailed("file:///b.png"))
        assertFalse(tracker.isCurrentlyThumbnailing("file:///a.png"))
        assertFalse(tracker.isCurrentlyThumbnailing("file:///b.png"))
    }

    @Test
    fun testEnsureThumbnailUnsupportedDoesNotMarkFailed() = runTest {
        val info = FileInfo(
            path = "/a.png", uri = "file:///a.png", name = "a.png",
            isDirectory = false, mimeType = "image/png", size = 1024
        )
        
        // Backend returns success(null) - not supported
        backend.markThumbnailUnsupported("file:///a.png")
        
        val path = tracker.ensureThumbnail(info)
        assertNull(path)
        
        // Should NOT be marked as failed
        assertFalse(tracker.hasFailed("file:///a.png"))
        assertFalse(tracker.isCurrentlyThumbnailing("file:///a.png"))
    }
}
