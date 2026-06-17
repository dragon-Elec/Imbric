package com.imbric.core.ifs.backends

import org.gnome.gio.File
import org.gnome.gio.Gio
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class UriTest {
    @Test
    fun testUriSpaces() {
        Gio.`javagi$ensureInitialized`()
        val f1 = File.forUri("file:///tmp/my#folder")
        println("f1 path: ${f1.path}")
    }
}
