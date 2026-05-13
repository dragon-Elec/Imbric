package com.imbric.core.ifs

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PathCapabilitiesTest {

    @Test
    fun testLocalFilePath() {
        val path = classifyPath("/home/user/document.txt")
        assertEquals("file", path.scheme)
        assertTrue(path.isNative)
        assertTrue(path.isWritable)
        assertFalse(path.isVirtual)
        assertTrue(path.isLocalFile)
        assertFalse(path.isRecent)
        assertFalse(path.isTrash)
    }

    @Test
    fun testExplicitFileUri() {
        val path = classifyPath("file:///home/user/document.txt")
        assertEquals("file", path.scheme)
        assertTrue(path.isNative)
        assertTrue(path.isWritable)
    }

    @Test
    fun testSmbUri() {
        val path = classifyPath("smb://server/share/doc.txt")
        assertEquals("smb", path.scheme)
        assertFalse(path.isNative)
        assertTrue(path.isWritable)
        assertFalse(path.isLocalFile)
    }

    @Test
    fun testRecentUri() {
        val path = classifyPath("recent://")
        assertEquals("recent", path.scheme)
        assertTrue(path.isNative)
        assertFalse(path.isWritable)
        assertTrue(path.isVirtual)
        assertTrue(path.isRecent)
    }

    @Test
    fun testTrashUri() {
        val path = classifyPath("trash://")
        assertEquals("trash", path.scheme)
        assertTrue(path.isNative)
        assertTrue(path.isWritable)
        assertFalse(path.isVirtual)
        assertTrue(path.isTrash)
    }
}
