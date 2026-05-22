@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.test.*
import kotlin.uuid.ExperimentalUuidApi

class FileInfoSelinuxTest {
    @Test
    fun `test FileInfo with SELinux context`() {
        val info = FileInfo(
            name = "secret.txt",
            path = "/home/user/secret.txt",
            uri = "file:///home/user/secret.txt",
            isDirectory = false,
            selinuxContext = "unconfined_u:object_r:user_home_t:s0"
        )
        assertEquals("unconfined_u:object_r:user_home_t:s0", info.selinuxContext)
    }

    @Test
    fun `test FileInfo without SELinux context defaults to null`() {
        val info = FileInfo(
            name = "file.txt",
            path = "/tmp/file.txt",
            uri = "file:///tmp/file.txt",
            isDirectory = false
        )
        assertNull(info.selinuxContext)
    }
}
