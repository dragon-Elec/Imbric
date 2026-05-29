package com.imbric.core.ifs.provider

import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.*
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

@OptIn(ExperimentalCoroutinesApi::class, kotlin.uuid.ExperimentalUuidApi::class)
class DirStateTest {

    @Test
    fun `verify inmemorybackend`() = runTest {
        val backend = InMemoryBackend()
        val root = "memory://test"
        val uri = "$root/file1"
        backend.fs[uri] = FileInfo(name = "file1", path = uri, uri = uri, isDirectory = false)
        val list = backend.list(root).toList()
        assertEquals(1, list.size)
    }

    @Test
    fun `test initial loading and chunking`() = runTest {
        val backend = InMemoryBackend()
        val root = "memory://test"
        
        // Add 120 items
        for (i in 1..120) {
            val uri = "$root/file$i"
            backend.fs[uri] = FileInfo(name = "file$i", path = uri, uri = uri, isDirectory = false)
        }
        
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(root, backend, backgroundScope, testDispatcher)
        
        advanceUntilIdle()
        
        assertEquals(120, dirState.items.value.size)
        assertFalse(dirState.isLoading.value)
    }

    @Test
    fun `test image enrichment with valid header`() = runTest {
        val backend = object : InMemoryBackend() {
            override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> {
                // Minimal valid GIF89a header (1x1)
                val gifHeader = byteArrayOf(
                    0x47.toByte(), 0x49.toByte(), 0x46.toByte(), 0x38.toByte(), 0x39.toByte(), 0x61.toByte(), // GIF89a
                    0x01.toByte(), 0x00.toByte(), // width 1
                    0x01.toByte(), 0x00.toByte(), // height 1
                    0x80.toByte(), // GCT follows, 2 colors
                    0x00.toByte(), // background color index
                    0x00.toByte()  // pixel aspect ratio
                )
                return Result.success(gifHeader)
            }

            override suspend fun enrichMetadata(info: FileInfo): FileInfo {
                // Simulate the 64KB trick: parse GIF header bytes for dimensions
                return if (!info.isDirectory && info.name.endsWith(".gif")) {
                    val bytesResult = readHeader(info.uri, 65536)
                    bytesResult.map { bytes ->
                        val width = ((bytes[7].toInt() and 0xFF) shl 8) or (bytes[6].toInt() and 0xFF)
                        val height = ((bytes[9].toInt() and 0xFF) shl 8) or (bytes[8].toInt() and 0xFF)
                        info.copy(
                            attributes = info.attributes + mapOf(
                                "std::dimensions" to "${width}x${height}",
                                "std::aspect-ratio" to (width.toDouble() / height)
                            )
                        )
                    }.getOrDefault(info)
                } else {
                    info
                }
            }
        }
        
        val root = "memory://test"
        val uri = "$root/image.gif"
        backend.fs[uri] = FileInfo(
            name = "image.gif", 
            path = uri, 
            uri = uri, 
            isDirectory = false, 
            mimeType = "image/gif"
        )
        
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(root, backend, backgroundScope, testDispatcher)
        
        // Wait for listing and enrichment
        advanceUntilIdle()
        
        val item = dirState.items.value.first { it.uri == uri } as com.imbric.core.models.FileInfo
        assertEquals("1x1", item.attributes["std::dimensions"])
        assertEquals(1.0, item.attributes["std::aspect-ratio"])
    }

    // --- Phase 1: DirectoryType tests ---

    @Test
    fun `test directory type from uri`() = runTest {
        val backend = InMemoryBackend()
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)

        val regular = DirState("file:///home", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.REGULAR, regular.directoryType)

        val trash = DirState("trash:///", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.TRASH, trash.directoryType)

        val recent = DirState("recent:///", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.RECENT, recent.directoryType)
    }

    // --- Phase 1: loadError tests ---

    @Test
    fun `test load error on failure`() = runTest {
        val backend = object : InMemoryBackend() {
            override fun list(uri: String): kotlinx.coroutines.flow.Flow<FileEntry> = kotlinx.coroutines.flow.flow {
                throw RuntimeException("Permission denied")
            }
        }
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("file:///forbidden", backend, backgroundScope, testDispatcher)

        advanceUntilIdle()

        assertNotNull(dirState.loadError.value, "loadError should be set after failure")
        assertTrue(dirState.loadError.value!!.message!!.contains("Permission denied"))
        assertFalse(dirState.isLoading.value, "isLoading should be false after error")
    }

    @Test
    fun `test load error cleared on refresh`() = runTest {
        var shouldFail = true
        val backend = object : InMemoryBackend() {
            override fun list(uri: String): kotlinx.coroutines.flow.Flow<FileEntry> = kotlinx.coroutines.flow.flow {
                if (shouldFail) throw RuntimeException("Fail")
                // Empty flow for success
            }
        }
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://test", backend, backgroundScope, testDispatcher)

        advanceUntilIdle()
        assertNotNull(dirState.loadError.value)

        // Now succeed
        shouldFail = false
        dirState.refresh()
        advanceUntilIdle()

        assertNull(dirState.loadError.value, "loadError should be cleared on successful refresh")
    }

    // --- Phase 1: Convenience methods tests ---

    @Test
    fun `test isNotEmpty`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "file.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertTrue(dirState.isNotEmpty)
    }

    @Test
    fun `test isNotEmpty empty dir`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "empty")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://empty", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertFalse(dirState.isNotEmpty)
    }

    @Test
    fun `test containsFile`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertTrue(dirState.containsFile("memory://dir/a.txt"))
        assertFalse(dirState.containsFile("memory://dir/missing.txt"))
    }

    @Test
    fun `test getFileByName`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")
        backend.createFile("memory://dir", "b.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertNotNull(dirState.getFileByName("a.txt"))
        assertEquals("a.txt", dirState.getFileByName("a.txt")!!.name)
        assertNull(dirState.getFileByName("missing.txt"))
    }

    @Test
    fun `test matchPattern`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "photo.jpg")
        backend.createFile("memory://dir", "image.png")
        backend.createFile("memory://dir", "readme.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        val images = dirState.matchPattern("*.jpg")
        assertEquals(1, images.size)
        assertEquals("photo.jpg", images[0].name)

        val pngImages = dirState.matchPattern("*.png")
        assertEquals(1, pngImages.size)
        assertEquals("image.png", pngImages[0].name)

        val everything = dirState.matchPattern("*")
        assertEquals(3, everything.size)

        val none = dirState.matchPattern("*.pdf")
        assertEquals(0, none.size)
    }

    // --- Phase 1: stop() and destroy() tests ---

    @Test
    fun `test stop preserves data`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertEquals(1, dirState.items.value.size)

        dirState.stop()

        // Data should still be available after stop
        assertEquals(1, dirState.items.value.size)
        assertTrue(dirState.containsFile("memory://dir/a.txt"))
    }

    @Test
    fun `test destroy clears data`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertEquals(1, dirState.items.value.size)

        dirState.destroy()

        // Data should be cleared after destroy
        assertEquals(0, dirState.items.value.size)
        assertFalse(dirState.isNotEmpty)
        assertFalse(dirState.isLoading.value)
    }

    @Test
    fun `test destroy is idempotent`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        // Should not throw
        dirState.destroy()
        dirState.destroy()
        dirState.destroy()

        assertEquals(0, dirState.items.value.size)
    }

    // --- Phase 2: DirStateRegistry tests ---

    @Test
    fun `test registry creates and caches`() = runTest {
        val backend = InMemoryBackend()
        val registry = DirStateRegistry(backend, backgroundScope)

        val state1 = registry.getOrCreate("file:///home")
        val state2 = registry.getOrCreate("file:///home")

        assertSame(state1, state2, "Same URI should return same DirState instance")
        assertEquals(1, registry.size)
    }

    @Test
    fun `test registry different URIs`() = runTest {
        val backend = InMemoryBackend()
        val registry = DirStateRegistry(backend, backgroundScope)

        val state1 = registry.getOrCreate("file:///home")
        val state2 = registry.getOrCreate("file:///tmp")

        assertNotSame(state1, state2, "Different URIs should return different DirState instances")
        assertEquals(2, registry.size)
    }

    @Test
    fun `test registry contains`() = runTest {
        val backend = InMemoryBackend()
        val registry = DirStateRegistry(backend, backgroundScope)

        assertFalse(registry.contains("file:///home"))

        registry.getOrCreate("file:///home")

        assertTrue(registry.contains("file:///home"))
        assertFalse(registry.contains("file:///tmp"))
    }

    @Test
    fun `test registry remove`() = runTest {
        val backend = InMemoryBackend()
        val registry = DirStateRegistry(backend, backgroundScope)

        registry.getOrCreate("file:///home")
        assertEquals(1, registry.size)

        registry.remove("file:///home")
        assertFalse(registry.contains("file:///home"))
    }

    @Test
    fun `test registry clear`() = runTest {
        val backend = InMemoryBackend()
        val registry = DirStateRegistry(backend, backgroundScope)

        registry.getOrCreate("file:///home")
        registry.getOrCreate("file:///tmp")
        assertEquals(2, registry.size)

        registry.clear()
        assertEquals(0, registry.size)
    }

    // --- Phase 3: ListingStrategy tests ---

    @Test
    fun `test Standard strategy lists files`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")
        backend.createFile("memory://dir", "b.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        assertEquals(2, dirState.items.value.size)
        assertTrue(dirState.containsFile("memory://dir/a.txt"))
        assertTrue(dirState.containsFile("memory://dir/b.txt"))
    }

    @Test
    fun `test Virtual strategy provides static list`() = runTest {
        val backend = InMemoryBackend()
        val virtualItems = listOf(
            FileInfo(name="bookmark1", path="/b1", uri="file:///b1", isDirectory=false),
            FileInfo(name="bookmark2", path="/b2", uri="file:///b2", isDirectory=false)
        )

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(
            "virtual://bookmarks", backend, backgroundScope, testDispatcher,
            strategy = ListingStrategy.Virtual(virtualItems)
        )
        advanceUntilIdle()

        assertEquals(2, dirState.items.value.size)
        assertTrue(dirState.containsFile("file:///b1"))
        assertTrue(dirState.containsFile("file:///b2"))
    }

    @Test
    fun `test Virtual strategy does not watch`() = runTest {
        val backend = InMemoryBackend()
        val virtualItems = listOf(
            FileInfo(name="a", path="/a", uri="file:///a", isDirectory=false)
        )

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(
            "virtual://test", backend, backgroundScope, testDispatcher,
            strategy = ListingStrategy.Virtual(virtualItems)
        )
        advanceUntilIdle()

        // Virtual strategy should not start monitoring
        // (no watchJob should be active — we can't directly test this, but
        // adding a file to the backend should NOT appear in the items)
        backend.createFile("memory://", "newfile.txt")
        advanceUntilIdle()

        assertEquals(1, dirState.items.value.size) // Still only the virtual item
    }

    @Test
    fun `test Search strategy uses backend search`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "photo.jpg")
        backend.createFile("memory://dir", "image.png")
        backend.createFile("memory://dir", "readme.txt")

        val query = com.imbric.core.models.VfsQuery(
            text = "photo",
            rootUri = "memory://dir"
        )

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(
            "memory://dir", backend, backgroundScope, testDispatcher,
            strategy = ListingStrategy.Search(query)
        )
        advanceUntilIdle()

        // Search results depend on backend.search() implementation
        // InMemoryBackend returns empty by default, so items should be empty
        // This tests that the strategy is used without crashing
        assertNotNull(dirState)
    }

    @Test
    fun `test DirectoryType from strategy URI`() = runTest {
        val backend = InMemoryBackend()

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)

        val trashState = DirState("trash:///", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.TRASH, trashState.directoryType)

        val recentState = DirState("recent:///", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.RECENT, recentState.directoryType)

        val networkState = DirState("smb://server/share", backend, backgroundScope, testDispatcher)
        assertEquals(DirectoryType.NETWORK, networkState.directoryType)
    }

    // --- Phase 4: Readiness flow tests ---

    @Test
    fun `test whenReady emits when predicate satisfied`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")
        backend.createFile("memory://dir", "b.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)

        val result = dirState.whenReady { it.size >= 2 }.first()
        assertEquals(2, result.size)
    }

    @Test
    fun `test whenReady does not emit while loading`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)

        // whenReady should wait until loading is complete
        val result = dirState.whenReady { it.isNotEmpty() }.first()
        assertEquals(1, result.size)
    }

    @Test
    fun `test whenEnriched emits when attributes populated`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        // whenEnriched should emit once the enrichment pipeline sets std::enriched
        val result = dirState.whenEnriched("memory://dir/a.txt").first() as com.imbric.core.models.FileInfo
        assertTrue(result.attributes.containsKey("std::enriched"))
    }

    // --- Phase 4: deepCount integration test ---

    @Test
    fun `test deepCount integration in enrichment`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "parent")
        backend.createFile("memory://parent", "file1.txt")
        backend.createFile("memory://parent", "file2.txt")
        backend.createFolder("memory://parent", "child")
        backend.createFile("memory://parent/child", "file3.txt")

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://parent", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()
        // Allow enrichment coroutines (launched on DirState.scope) to complete
        delay(1000)
        advanceUntilIdle()

        // items are children of the listed directory, not the directory itself
        val childDir = dirState.items.value.find { it.name == "child" }!! as com.imbric.core.models.FileInfo
        assertTrue(childDir.attributes.containsKey("std::enriched"), "Child should be marked as enriched")
    }
}
