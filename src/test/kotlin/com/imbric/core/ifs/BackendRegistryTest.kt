package com.imbric.core.ifs

import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertSame

class BackendRegistryTest {
    private lateinit var registry: BackendRegistry

    @BeforeTest
    fun setup() {
        registry = BackendRegistry()
        registry.register("memory", InMemoryBackend("memory"))
        registry.register("smb", InMemoryBackend("smb"))
        registry.setDefault(InMemoryBackend("file"))
    }

    @Test
    fun testGetIoByScheme() {
        val backend = registry.get("memory://foo/bar")
        assertEquals("memory", backend?.scheme)
    }

    @Test
    fun testGetIoFallbackToDefault() {
        val backend = registry.get("/home/user/foo.txt")
        assertEquals("file", backend?.scheme)
    }

    @Test
    fun testGetIoUnknownScheme() {
        val backend = registry.get("unknown://foo/bar")
        assertNull(backend)
    }

    @Test
    fun testGetRegisteredSchemes() {
        val schemes = registry.getRegisteredSchemes()
        assert(schemes.contains("memory"))
        assert(schemes.contains("smb"))
    }

    @Test
    fun testGetIoSmartRoutingCanHandle() {
        val customBackend = object : InMemoryBackend("custom") {
            override fun canHandle(uri: String): Boolean = uri.startsWith("magic://")
        }
        registry.register("custom", customBackend)
        val backend = registry.get("magic://foo/bar")
        assertEquals("custom", backend?.scheme)
    }
}
