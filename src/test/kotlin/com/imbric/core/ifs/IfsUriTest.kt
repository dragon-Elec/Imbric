package com.imbric.core.ifs

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class IfsUriTest {

    @Test
    fun testScheme() {
        assertEquals("file", IfsUri("file:///path/to/file.txt").scheme)
        assertEquals("smb", IfsUri("smb://server/share/file.txt").scheme)
        assertEquals("file", IfsUri("/path/to/file.txt").scheme) // default when missing
        assertEquals("trash", IfsUri("trash://").scheme)
        assertEquals("recent", IfsUri("recent://").scheme)
        assertEquals("sftp", IfsUri("sftp://user@host/path").scheme)
    }

    @Test
    fun testIsNative() {
        assertTrue(IfsUri("file:///path/to/file.txt").isNative)
        assertTrue(IfsUri("trash://").isNative)
        assertTrue(IfsUri("recent://").isNative)
        assertTrue(IfsUri("/path/to/file.txt").isNative) // defaults to file

        assertFalse(IfsUri("smb://server/share/file.txt").isNative)
        assertFalse(IfsUri("sftp://server/path").isNative)
    }

    @Test
    fun testName() {
        assertEquals("file.txt", IfsUri("file:///path/to/file.txt").name)
        assertEquals("path", IfsUri("file:///path/").name)
        assertEquals("path", IfsUri("file:///path").name)
        assertEquals("/", IfsUri("file:///").name)
        assertEquals("/", IfsUri("file://").name)
        assertEquals("/", IfsUri("/").name)
        assertEquals("share", IfsUri("smb://server/share").name)
        assertEquals("/", IfsUri("smb://").name)
        assertEquals("file.txt", "file:///path/to/file.txt".uriName)
    }

    @Test
    fun testParent() {
        assertEquals("file:///path/to", IfsUri("file:///path/to/file.txt").parent.uriString)
        assertEquals("file:///", IfsUri("file:///path").parent.uriString)
        assertEquals("file:///", IfsUri("file:///").parent.uriString)
        assertEquals("smb://server", IfsUri("smb://server/share").parent.uriString)
        assertEquals("smb:///", IfsUri("smb://server").parent.uriString)
        assertEquals("smb:///", IfsUri("smb:///").parent.uriString)
        assertEquals("/path/to", IfsUri("/path/to/file.txt").parent.uriString)
        assertEquals("/", IfsUri("/path").parent.uriString)
        assertEquals("/", IfsUri("/").parent.uriString)
        assertEquals("file:///path/to", "file:///path/to/file.txt".uriParent)
    }

    @Test
    fun testExtension() {
        assertEquals("txt", IfsUri("file:///path/to/file.txt").extension)
        assertEquals("gz", IfsUri("file:///path/to/archive.tar.gz").extension)
        assertEquals("", IfsUri("file:///path/to/file").extension)
        assertEquals("hidden", IfsUri("file:///path/to/.hidden").extension)
    }

    @Test
    fun testNameWithoutExtension() {
        assertEquals("file", IfsUri("file:///path/to/file.txt").nameWithoutExtension)
        assertEquals("archive.tar", IfsUri("file:///path/to/archive.tar.gz").nameWithoutExtension)
        assertEquals("file", IfsUri("file:///path/to/file").nameWithoutExtension)
        assertEquals("", IfsUri("file:///path/to/.hidden").nameWithoutExtension)
    }

    @Test
    fun testJoin() {
        assertEquals("file:///path/to/child", IfsUri("file:///path/to").join("child").uriString)
        assertEquals("file:///path/to/child", IfsUri("file:///path/to/").join("child").uriString)
        assertEquals("file:///path/to/child", IfsUri("file:///path/to").join("/child").uriString)
        assertEquals("file:///child", IfsUri("file:///").join("child").uriString)
        assertEquals("smb://server/child", IfsUri("smb://server").join("child").uriString)
        assertEquals("file:///path/to/child", "file:///path/to".uriJoin("child"))
    }

    @Test
    fun testRenameTarget() {
        assertEquals("file:///path/to/new_file.txt", IfsUri("file:///path/to/old_file.txt").renameTarget("new_file.txt").uriString)
        assertEquals("file:///new_file.txt", IfsUri("file:///old_file.txt").renameTarget("new_file.txt").uriString)
    }

    @Test
    fun testToString() {
        assertEquals("file:///path/to/file.txt", IfsUri("file:///path/to/file.txt").toString())
    }
}
