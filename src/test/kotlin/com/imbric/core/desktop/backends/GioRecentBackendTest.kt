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
}