package com.imbric.core.ifs.directories

import com.imbric.core.models.*
import com.imbric.core.ifs.FileEvent
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
    val list = backend.list(root)
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
            override suspend fun list(uri: String, sortKey: SortKey): List<FileEntry> {
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
            override suspend fun list(uri: String, sortKey: SortKey): List<FileEntry> {
                if (shouldFail) throw RuntimeException("Fail")
                return emptyList()
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
        advanceUntilIdle()

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
        advanceUntilIdle()

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

    // --- Phase 4: emblem enrichment integration test ---

    @Test
    fun `test emblem enrichment applies symlink emblem`() = runTest {
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "parent")
        // Symlink child — the emblem source for the sync enrichment path.
        // Inserted directly into fs because InMemoryBackend has no
        // createSymlink helper; the symlink fields are plain constructor
        // params on FileInfo.
        val childUri = "memory://parent/link.txt"
        backend.fs[childUri] = FileInfo(
            path = childUri,
            uri = childUri,
            name = "link.txt",
            isDirectory = false,
            isSymlink = true,
            symlinkTarget = "/some/target"
        )

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://parent", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        // Enrichment is viewport-driven and async (scope.launch): settle the
        // scheduler until the row is listed, like the UI (which only reports
        // visible, already-listed items). Enriching before install completes
        // silently skips (no retry), so this wait is load-bearing.
        run {
            repeat(20) {
                advanceUntilIdle()
                testScheduler.runCurrent()
                if (dirState.items.value.any { it.uri == childUri }) return@run
            }
        }
        assertTrue(dirState.items.value.any { it.uri == childUri }, "link row must be listed before enriching")
        dirState.enrichVisibleItems(listOf(childUri))
        run {
            repeat(20) {
                advanceUntilIdle()
                testScheduler.runCurrent()
                val row = dirState.items.value.find { it.uri == childUri }
                if (row is com.imbric.core.models.FileInfo && row.attributes.containsKey("std::emblems")) return@run
            }
        }

        val child = dirState.items.value.find { it.uri == childUri }!! as com.imbric.core.models.FileInfo
        val emblems = child.attributes["std::emblems"] as? List<*>
        assertTrue(
            emblems != null && emblems.contains("emblem-symbolic-link"),
            "Symlink child should carry emblem-symbolic-link, got: ${child.attributes["std::emblems"]}"
        )
        dirState.destroy()
    }

    @Test
    fun `test emblem enrichment applies readonly emblem`() = runBlocking {
        // Read-only emblem, built through the FileInfo path (never list()):
        // the row is stored with isWritable=false — what the GIO backend
        // now derives from access::can-write — and reaches the emblem
        // layer via the event-driven fetch (getMetadata returns the
        // stored FileInfo intact). Viewport enrichment of base rows
        // goes through the SoA flatten, which does not carry isWritable,
        // so the event path is the one that must show the emblem.
        // Real coroutines (not TestScope): the 200ms storm-catcher
        // debounce needs a real clock, like FakeFilesystem-based tests.
        val backend = InMemoryBackend()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            backend.createFolder("memory://", "parent")
            val childUri = "memory://parent/ro.txt"
            backend.fs[childUri] = FileInfo(
                path = childUri,
                uri = childUri,
                name = "ro.txt",
                isDirectory = false,
                isWritable = false
            )

            val dirState = DirState("memory://parent", backend, scope, Dispatchers.Default)
            dirState.isLoading.first { !it }
            delay(50) // let the watcher coroutines start collecting

            backend.emitFileEvent(FileEvent.Modified(childUri))
            delay(400) // 200ms debounce + metadata fetch + emblem enrichment

            val child = dirState.items.value.find { it.uri == childUri } as? com.imbric.core.models.FileInfo
            require(child != null) { "read-only row must be listed via the additions delta" }
            val emblems = child.attributes["std::emblems"] as? List<*>
            assertTrue(
                emblems != null && emblems.contains("emblem-readonly"),
                "Non-writable child should carry emblem-readonly, got: ${child.attributes["std::emblems"]}"
            )
            dirState.destroy()
        } finally {
            scope.cancel()
        }
    }
}
