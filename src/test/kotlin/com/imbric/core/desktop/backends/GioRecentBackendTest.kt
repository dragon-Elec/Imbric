@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.desktop.backends

import com.imbric.core.ifs.backends.GioRecentBackend
import com.imbric.core.models.FileJob
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.gnome.gio.Gio
import kotlin.test.assertTrue
import kotlin.test.assertIs

class GioRecentBackendTest {
    @BeforeEach
    fun setup() {
        Gio.`javagi$ensureInitialized`()
    }
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
        val job = FileJob(opType = "test", source = "recent:///test")

        val results = listOf(
            backend.getMetadata("recent:///test"),
            backend.readHeader("recent:///test", 1024),
            backend.trash(job, false),
            backend.restoreFromTrash("recent:///trash", "recent:///test"),
            backend.delete(job),
            backend.createFolder("recent:///", "newFolder"),
            backend.createFile("recent:///", "newFile.txt"),
            backend.rename("recent:///old.txt", "new.txt")
        )

        for (result in results) {
            assertTrue(result.isFailure, "Expected failure but got success")
            assertIs<UnsupportedOperationException>(result.exceptionOrNull())
        }
    }
}