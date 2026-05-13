@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Tag
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

@Tag("integration")
class GioTypeMappersIntegrationTest {

    private val backend = GioBackend()

    @Test
    fun testMetadataMappingToAttributes(@TempDir tempDir: Path) = runTest {
        val file = File(tempDir.toFile(), "mapping_test.txt")
        file.writeText("test content")
        val fileUri = "file://${file.absolutePath}"

        val result = backend.getMetadata(fileUri)
        assertTrue(result.isSuccess)
        
        val info = result.getOrThrow()
        
        // Check first-class fields
        assertEquals("mapping_test.txt", info.name)
        assertEquals(12L, info.size)
        
        // Check attributes bag (Secret Bag)
        val attrs = info.attributes
        assertTrue(attrs.isNotEmpty(), "Attributes bag should not be empty")
        
        // GIO attributes are prefixed with namespace (e.g. standard::size)
        // GioTypeMappers.toImbricFileInfo maps them as-is from getAttributeAsString
        
        assertNotNull(attrs["standard::size"], "standard::size should be in attributes")
        assertEquals("12", attrs["standard::size"].toString())
        
        assertNotNull(attrs["standard::display-name"], "standard::display-name should be in attributes")
        assertNotNull(attrs["standard::content-type"], "standard::content-type should be in attributes")
        
        // Check permissions in bag
        assertNotNull(attrs["access::can-read"])
        // GIO returns "TRUE" / "FALSE" for booleans via getAttributeAsString
        assertEquals("TRUE", attrs["access::can-read"].toString())
    }
}
