package com.imbric.core.testing

import com.imbric.core.ifs.FileEvent
import com.imbric.core.ifs.provider.DirState
import com.imbric.core.ifs.provider.DirStateRegistry
import com.imbric.core.models.FileEntry
import com.imbric.core.models.FileInfo
import com.imbric.core.models.SortKey
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

/**
 * High-level contract test wrapper.
 * Uses real coroutines (not TestScope) — InMemoryBackend has zero IO delay
 * so coroutines complete near-instantly.
 *
 * Contract tests use ONLY this class. If internals change, only this class needs updating.
 */
class FakeFilesystem {

    val backend = InMemoryBackend()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val registry = DirStateRegistry(backend, scope)
    private val activeDirs = mutableMapOf<String, DirState>()

    // ── Filesystem setup ──────────────────────────────────────────────

    fun createFile(
        path: String,
        size: Long = 0,
        mimeType: String = "text/plain",
        isHidden: Boolean = false,
        isDirectory: Boolean = false
    ) {
        val name = path.substringAfterLast("/")
        backend.fs[path] = FileInfo(
            path = path, uri = path, name = name, displayName = name,
            isDirectory = isDirectory, isSymlink = false, symlinkTarget = null,
            size = size, mimeType = mimeType,
            modifiedTime = kotlin.time.Clock.System.now(),
            isHidden = isHidden, isWritable = true,
            iconName = if (isDirectory) "folder" else "text-x-generic"
        )
    }

    fun createFolder(path: String) {
        createFile(path, isDirectory = true, mimeType = "inode/directory")
    }

    fun createFiles(vararg paths: String) {
        paths.forEach { createFile(it) }
    }

    fun deleteFile(path: String) {
        backend.fs.remove(path)
    }

    fun fileExists(path: String): Boolean = backend.fs.containsKey(path)

    fun filesystemContents(dirUri: String): List<String> {
        val normalized = dirUri.removeSuffix("/")
        return backend.fs.values
            .filter { it.uri.startsWith("$normalized/") && it.uri != normalized
                    && !it.uri.removePrefix("$normalized/").contains("/") }
            .map { it.name }.sorted()
    }

    // ── Directory observation ─────────────────────────────────────────

    fun openDir(dirUri: String, sortKey: SortKey = SortKey.NAME): DirView {
        val dirState = registry.getOrCreate(dirUri)
        activeDirs[dirUri] = dirState
        runBlocking {
            dirState.isLoading.first { !it }
            // Small delay to let watcher coroutines start collecting after refresh completes
            delay(50)
        }
        return DirView(dirState, dirUri)
    }

    // ── Event simulation ──────────────────────────────────────────────

    fun simulateFileCreated(path: String) = backend.emitFileEvent(FileEvent.Created(path))
    fun simulateFileDeleted(path: String) = backend.emitFileEvent(FileEvent.Deleted(path))
    fun simulateFileModified(path: String) = backend.emitFileEvent(FileEvent.Modified(path))
    fun simulateFileRenamed(from: String, to: String) = backend.emitFileEvent(FileEvent.Renamed(from, to))

    // ── Helpers ───────────────────────────────────────────────────────

    fun destroy() {
        activeDirs.values.forEach { it.destroy() }
        activeDirs.clear()
        registry.clear()
        scope.cancel()
    }

    // ── DirView ───────────────────────────────────────────────────────

    class DirView(private val dirState: DirState, private val dirUri: String) {

        val items: List<FileEntry> get() = dirState.items.value
        val isLoading: Boolean get() = dirState.isLoading.value
        val error: Exception? get() = dirState.loadError.value
        val names: List<String> get() = items.map { it.name }.sorted()

        fun assertShowsExactly(vararg expectedNames: String) {
            assertEquals(expectedNames.sorted(), names, "Items mismatch")
        }

        fun assertContains(name: String) {
            assertTrue(names.contains(name), "Expected '$name' in $names")
        }

        fun assertNotContains(name: String) {
            assertFalse(names.contains(name), "Expected NOT '$name' in $names")
        }

        fun assertEmpty() { assertTrue(items.isEmpty(), "Expected empty, got ${items.size}") }
        fun assertSize(expected: Int) { assertEquals(expected, items.size) }
        fun assertOrder(vararg expectedNames: String) {
            assertEquals(expectedNames.toList(), items.map { it.name })
        }
        fun assertLoading() { assertTrue(isLoading) }
        fun assertNotLoading() { assertFalse(isLoading) }
        fun assertHasError() { assertTrue(error != null) }
        fun assertNoError() { assertEquals(null, error) }

        /** Wait for items to satisfy a predicate. Uses real delays. */
        fun waitUntil(timeoutMs: Long = 2000, predicate: (List<FileEntry>) -> Boolean) {
            val deadline = System.currentTimeMillis() + timeoutMs
            while (System.currentTimeMillis() < deadline) {
                if (predicate(items)) return
                runBlocking { delay(50) }
            }
            throw AssertionError("Timed out. Current: ${items.map { it.name }}")
        }
    }
}
