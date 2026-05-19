@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.provider

import kotlin.test.Test
import kotlin.test.assertEquals

class DirectoryTypeTest {

    @Test
    fun testFromUriFile() {
        assertEquals(DirectoryType.REGULAR, DirectoryType.fromUri("file:///home/user"))
        assertEquals(DirectoryType.REGULAR, DirectoryType.fromUri("file:///"))
    }

    @Test
    fun testFromUriBarePath() {
        // Bare paths (no scheme) default to REGULAR
        assertEquals(DirectoryType.REGULAR, DirectoryType.fromUri("/home/user"))
    }

    @Test
    fun testFromUriTrash() {
        assertEquals(DirectoryType.TRASH, DirectoryType.fromUri("trash:///"))
        assertEquals(DirectoryType.TRASH, DirectoryType.fromUri("trash://"))
    }

    @Test
    fun testFromUriRecent() {
        assertEquals(DirectoryType.RECENT, DirectoryType.fromUri("recent:///"))
    }

    @Test
    fun testFromUriStarred() {
        assertEquals(DirectoryType.STARRED, DirectoryType.fromUri("starred:///"))
    }

    @Test
    fun testFromUriSearch() {
        assertEquals(DirectoryType.SEARCH, DirectoryType.fromUri("search://query"))
    }

    @Test
    fun testFromUriNetwork() {
        assertEquals(DirectoryType.NETWORK, DirectoryType.fromUri("smb://server/share"))
        assertEquals(DirectoryType.NETWORK, DirectoryType.fromUri("sftp://server/home"))
        assertEquals(DirectoryType.NETWORK, DirectoryType.fromUri("ftp://server/files"))
        assertEquals(DirectoryType.NETWORK, DirectoryType.fromUri("mtp://device/storage"))
    }

    @Test
    fun testFromUriOther() {
        assertEquals(DirectoryType.OTHER, DirectoryType.fromUri("custom://something"))
    }

    @Test
    fun testFromUriCaseInsensitive() {
        assertEquals(DirectoryType.TRASH, DirectoryType.fromUri("TRASH:///"))
        assertEquals(DirectoryType.NETWORK, DirectoryType.fromUri("SMB://server/share"))
    }
}
