package com.imbric.core.desktop

import com.imbric.core.ifs.BackendRegistry
import kotlin.test.Test
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class ImbricDesktopTest {
    @Test
    fun testInitializeRegistersExpectedSchemes() {
        ImbricDesktop.initialize()

        // Verify that the schemes were registered correctly.
        // Even though getRegisteredSchemes() exists, we can also verify by fetching them.
        assertNotNull(BackendRegistry.getIo("file://"))
        assertNotNull(BackendRegistry.getIo("trash://"))
        assertNotNull(BackendRegistry.getIo("smb://"))
        assertNotNull(BackendRegistry.getIo("sftp://"))
        assertNotNull(BackendRegistry.getIo("recent://"))
        assertNotNull(BackendRegistry.getIo("search://"))

        // Also verify with getRegisteredSchemes if we want
        val registeredSchemes = BackendRegistry.getRegisteredSchemes()
        assertTrue(registeredSchemes.contains("file"))
        assertTrue(registeredSchemes.contains("trash"))
        assertTrue(registeredSchemes.contains("smb"))
        assertTrue(registeredSchemes.contains("sftp"))
        assertTrue(registeredSchemes.contains("recent"))
        assertTrue(registeredSchemes.contains("search"))
    }
}
