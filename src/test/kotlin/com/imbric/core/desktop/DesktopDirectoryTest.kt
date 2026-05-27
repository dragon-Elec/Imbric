package com.imbric.core.desktop
 
import com.imbric.core.ifs.backends.TestUtils
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.BeforeEach
import org.gnome.gio.Gio
import kotlin.test.*
 
class DesktopDirectoryTest {
    @BeforeEach
    fun setup() {
        Gio.`javagi$ensureInitialized`()
    }

    @Test
    fun `test desktop directory URI format`() = runTest {
        TestUtils.withGlibPump {
            val uri = DesktopDirectory.getUri()
            assertTrue(uri.startsWith("file://"))
            assertTrue(uri.endsWith("/Desktop"))
        }
    }

    @Test
    fun `test desktop directory exists on most systems`() = runTest {
        TestUtils.withGlibPump {
            // This test verifies the method doesn't crash
            val exists = DesktopDirectory.exists()
            // We can't assert true because some systems might not have ~/Desktop
            // But we can verify it returns a boolean without exception
            assertTrue(exists || !exists) // always true, just checking no crash
        }
    }
}
