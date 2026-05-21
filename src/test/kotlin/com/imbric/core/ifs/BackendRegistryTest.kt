package com.imbric.core.ifs

import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.test.runTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertSame

class BackendRegistryTest {

    @BeforeTest
    fun setup() {
        // Resetting singleton state using reflection or by creating a fresh object is hard.
        // Instead, we just register what we need. 
        BackendRegistry.registerIo("memory", InMemoryBackend("memory"))
        BackendRegistry.registerIo("smb", InMemoryBackend("smb"))
        BackendRegistry.setDefaultIo(InMemoryBackend("file"))
    }

    @Test
    fun testGetIoByScheme() {
        val backend = BackendRegistry.getIo("memory://foo/bar")
        assertEquals("memory", backend?.scheme)
    }

    @Test
    fun testGetIoFallbackToDefault() {
        val backend = BackendRegistry.getIo("/home/user/foo.txt")
        assertEquals("file", backend?.scheme)
    }

    @Test
    fun testGetIoUnknownScheme() {
        val backend = BackendRegistry.getIo("unknown://foo/bar")
        assertNull(backend)
    }

    @Test
    fun testGetRegisteredSchemes() {
        val schemes = BackendRegistry.getRegisteredSchemes()
        assert(schemes.contains("memory"))
        assert(schemes.contains("smb"))
    }

    @Test
    fun testGetIoSmartRoutingCanHandle() {
        val customBackend = object : InMemoryBackend("custom") {
            override fun canHandle(uri: String): Boolean = uri.startsWith("magic://")
        }
        BackendRegistry.registerIo("custom", customBackend)
        val backend = BackendRegistry.getIo("magic://foo/bar")
        assertEquals("custom", backend?.scheme)
    }
}
