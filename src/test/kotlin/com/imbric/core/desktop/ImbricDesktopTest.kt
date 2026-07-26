package com.imbric.core.desktop
 
import org.junit.jupiter.api.BeforeEach
import org.gnome.gio.Gio
import kotlin.test.Test
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gnome.gtk.Gtk
import org.gnome.gio.Vfs
 
class ImbricDesktopTest {
    @BeforeEach
    fun setup() {
        Gio.`javagi$ensureInitialized`()
    }

    @Test
    fun testInitializeRegistersExpectedSchemes() {
        if (!Gtk.isInitialized()) Gtk.init()

        val registry = ImbricDesktop.initialize()

        assertNotNull(registry.get("file://"))
        assertNotNull(registry.get("trash://"))
        assertNotNull(registry.get("recent://"))
        assertNotNull(registry.get("search://"))

        val vfs = Vfs.getDefault()
        val supported = vfs.supportedUriSchemes?.toList() ?: emptyList()

        if (supported.contains("smb")) {
            assertNotNull(registry.get("smb://"))
        }
        if (supported.contains("sftp")) {
            assertNotNull(registry.get("sftp://"))
        }

        // Also verify with getRegisteredSchemes if we want
        val registeredSchemes = registry.getRegisteredSchemes()
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
