package com.imbric.core.ifs.backends

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeAll
import org.jetbrains.skiko.Library
import org.jetbrains.skia.Codec
import org.jetbrains.skia.Data
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SkiaCodecTest {
    companion object {
        @JvmStatic
        @BeforeAll
        fun setup() {
            Library.load()
        }
    }

    @Test
    fun testSkiaCodecDimensionsWithPng() {
        val image = java.awt.image.BufferedImage(1, 1, java.awt.image.BufferedImage.TYPE_INT_ARGB)
        val bos = java.io.ByteArrayOutputStream()
        javax.imageio.ImageIO.write(image, "png", bos)
        val pngBytes = bos.toByteArray()
        
        val data = Data.makeFromBytes(pngBytes)
        val codec = Codec.makeFromData(data)
        assertNotNull(codec)
        assertEquals(1, codec.width)
        assertEquals(1, codec.height)
    }

    @Test
    fun testSkiaCodecWithRealImages() {
        val picturesDir = File(System.getProperty("user.home"), "Pictures")
        if (!picturesDir.isDirectory) {
            println("Pictures directory not found, skipping real image test.")
            return
        }

        // Find any PNG or JPG files in Pictures or Screenshots
        val imageFiles = picturesDir.walkTopDown()
            .filter { it.isFile && (it.name.endsWith(".png", ignoreCase = true) || it.name.endsWith(".jpg", ignoreCase = true) || it.name.endsWith(".jpeg", ignoreCase = true)) }
            .take(5)
            .toList()

        if (imageFiles.isEmpty()) {
            println("No real images found in Pictures directory, skipping real image test.")
            return
        }

        for (file in imageFiles) {
            println("Testing real image: ${file.absolutePath}")
            // Read first 64KB
            val bytes = file.inputStream().use { input ->
                val buffer = ByteArray(65536)
                val read = input.read(buffer)
                if (read > 0) buffer.copyOf(read) else ByteArray(0)
            }

            assertTrue(bytes.isNotEmpty(), "Bytes read from ${file.name} should not be empty")
            val data = Data.makeFromBytes(bytes)
            val codec = Codec.makeFromData(data)
            assertNotNull(codec, "Codec should be created successfully for ${file.name}")
            assertTrue(codec.width > 0, "Width should be positive for ${file.name}")
            assertTrue(codec.height > 0, "Height should be positive for ${file.name}")
            println("  Dimensions: ${codec.width}x${codec.height}")
        }
    }
}
