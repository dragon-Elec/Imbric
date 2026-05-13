package com.imbric.core.ifs.provider

import com.imbric.core.models.FileInfo
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.*
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

@OptIn(ExperimentalCoroutinesApi::class, kotlin.uuid.ExperimentalUuidApi::class)
class DirStateTest {

    @Test
    fun `verify inmemorybackend`() = runTest {
        val backend = InMemoryBackend()
        val root = "memory://test"
        val uri = "$root/file1"
        backend.fs[uri] = FileInfo(name = "file1", path = uri, uri = uri, isDirectory = false)
        val list = backend.list(root).toList()
        assertEquals(1, list.size)
    }

    @Test
    fun `test initial loading and chunking`() = runTest {
        val backend = InMemoryBackend()
        val root = "memory://test"
        
        // Add 120 items
        for (i in 1..120) {
            val uri = "$root/file$i"
            backend.fs[uri] = FileInfo(name = "file$i", path = uri, uri = uri, isDirectory = false)
        }
        
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(root, backend, backgroundScope, testDispatcher)
        
        advanceUntilIdle()
        
        assertEquals(120, dirState.items.value.size)
        assertFalse(dirState.isLoading.value)
    }

    @Test
    fun `test image enrichment with valid header`() = runTest {
        val backend = object : InMemoryBackend() {
            override suspend fun readHeader(uri: String, size: Long): Result<ByteArray> {
                // Minimal valid GIF89a header (1x1)
                val gifHeader = byteArrayOf(
                    0x47.toByte(), 0x49.toByte(), 0x46.toByte(), 0x38.toByte(), 0x39.toByte(), 0x61.toByte(), // GIF89a
                    0x01.toByte(), 0x00.toByte(), // width 1
                    0x01.toByte(), 0x00.toByte(), // height 1
                    0x80.toByte(), // GCT follows, 2 colors
                    0x00.toByte(), // background color index
                    0x00.toByte()  // pixel aspect ratio
                )
                return Result.success(gifHeader)
            }

            override suspend fun enrichMetadata(info: FileInfo): FileInfo {
                // Simulate the 64KB trick: parse GIF header bytes for dimensions
                return if (!info.isDirectory && info.name.endsWith(".gif")) {
                    val bytesResult = readHeader(info.uri, 65536)
                    bytesResult.map { bytes ->
                        val width = ((bytes[7].toInt() and 0xFF) shl 8) or (bytes[6].toInt() and 0xFF)
                        val height = ((bytes[9].toInt() and 0xFF) shl 8) or (bytes[8].toInt() and 0xFF)
                        info.copy(
                            attributes = info.attributes + mapOf(
                                "std::dimensions" to "${width}x${height}",
                                "std::aspect-ratio" to (width.toDouble() / height)
                            )
                        )
                    }.getOrDefault(info)
                } else {
                    info
                }
            }
        }
        
        val root = "memory://test"
        val uri = "$root/image.gif"
        backend.fs[uri] = FileInfo(
            name = "image.gif", 
            path = uri, 
            uri = uri, 
            isDirectory = false, 
            mimeType = "image/gif"
        )
        
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(root, backend, backgroundScope, testDispatcher)
        
        // Wait for listing and enrichment
        advanceUntilIdle()
        
        val item = dirState.items.value.first { it.uri == uri }
        assertEquals("1x1", item.attributes["std::dimensions"])
        assertEquals(1.0, item.attributes["std::aspect-ratio"])
    }
}
