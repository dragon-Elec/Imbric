package com.imbric.core.desktop

import com.imbric.core.ifs.BackendRegistry
import kotlin.test.Test
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gnome.gtk.Gtk
import org.gnome.gio.Vfs

class ImbricDesktopTest {
    @Test
    fun testInitializeRegistersExpectedSchemes() {
        if (!Gtk.isInitialized()) Gtk.init()

        ImbricDesktop.initialize()

        assertNotNull(BackendRegistry.getIo("file://"))
        assertNotNull(BackendRegistry.getIo("trash://"))
        assertNotNull(BackendRegistry.getIo("recent://"))
        assertNotNull(BackendRegistry.getIo("search://"))

        val vfs = Vfs.getDefault()
        val supported = vfs.supportedUriSchemes?.toList() ?: emptyList()

        if (supported.contains("smb")) {
            assertNotNull(BackendRegistry.getIo("smb://"))
        }
        if (supported.contains("sftp")) {
            assertNotNull(BackendRegistry.getIo("sftp://"))
        }

        // Also verify with getRegisteredSchemes if we want
        val registeredSchemes = BackendRegistry.getRegisteredSchemes()
        assertTrue(registeredSchemes.contains("file"))
        assertTrue(registeredSchemes.contains("trash"))
        assertTrue(registeredSchemes.contains("recent"))
        assertTrue(registeredSchemes.contains("search"))

        if (supported.contains("smb")) {
            assertTrue(registeredSchemes.contains("smb"))
        }
        if (supported.contains("sftp")) {
            assertTrue(registeredSchemes.contains("sftp"))
        }
    }
}
