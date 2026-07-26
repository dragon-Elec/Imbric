@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.desktop.backends

import com.imbric.core.ifs.backends.gio.GioRecentBackend
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.flow.first
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
        val items = backend.list("recent:///").first()
        println("GioRecentBackend returned ${items.size} items")
        // Note: size might be 0 if the user has no recent items, but it shouldn't crash.
        assertTrue(items != null)
    }

    // Removed old stub-method checks (trash, delete, createFolder, etc.)
    // GioRecentBackend now only implements BackendContract + RecentContract.
    // WriteContract and TrashContract methods no longer exist on this class.
    @Test
    fun testUnsupportedMetadataOperations() = runBlocking {
        val backend = GioRecentBackend()

        val results = listOf(
            backend.getMetadata("recent:///test"),
            backend.readHeader("recent:///test", 1024),
        )

        for (result in results) {
            assertTrue(result.isFailure, "Expected failure but got success")
            assertIs<UnsupportedOperationException>(result.exceptionOrNull())
        }
    }
}