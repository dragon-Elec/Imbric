package com.imbric.core.desktop

import kotlin.test.*

class SandboxDetectorTest {
    @Test
    fun `test sandbox detection does not crash`() {
        // Just verify the properties are accessible without exception
        val isFlatpak = SandboxDetector.isFlatpak
        val isSnap = SandboxDetector.isSnap
        val isSandboxed = SandboxDetector.isSandboxed
        val type = SandboxDetector.sandboxType

        // On a normal desktop, these should all be false/null
        // (unless actually running in Flatpak/Snap)
        if (!isFlatpak && !isSnap) {
            assertFalse(isSandboxed)
            assertNull(type)
        }
    }

    @Test
    fun `test sandbox type consistency`() {
        val type = SandboxDetector.sandboxType
        if (type != null) {
            assertTrue(SandboxDetector.isSandboxed)
            assertTrue(type == "flatpak" || type == "snap")
        }
    }
}
