@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.models

import kotlin.test.*
import kotlin.uuid.ExperimentalUuidApi

class VfsQueryTest {
    @Test
    fun `test default VfsQuery values`() {
        val query = VfsQuery(text = "test", rootUri = "file:///home")
        assertEquals("test", query.text)
        assertEquals("file:///home", query.rootUri)
        assertNull(query.mimeFilter)
        assertTrue(query.recursive)
        assertFalse(query.includeHidden)
        assertEquals(Int.MAX_VALUE, query.maxDepth)
        assertFalse(query.contentSearch)
        assertNull(query.modifiedAfter)
        assertNull(query.modifiedBefore)
        assertNull(query.minSize)
        assertNull(query.maxSize)
        assertFalse(query.starredOnly)
    }

    @Test
    fun `test VfsQuery with date range filter`() {
        val query = VfsQuery(
            text = "report",
            rootUri = "file:///home",
            modifiedAfter = 1000L,
            modifiedBefore = 2000L
        )
        assertEquals(1000L, query.modifiedAfter)
        assertEquals(2000L, query.modifiedBefore)
    }

    @Test
    fun `test VfsQuery with size range filter`() {
        val query = VfsQuery(
            text = "photo",
            rootUri = "file:///home",
            minSize = 1024L,
            maxSize = 10485760L
        )
        assertEquals(1024L, query.minSize)
        assertEquals(10485760L, query.maxSize)
    }

    @Test
    fun `test VfsQuery with all filters combined`() {
        val query = VfsQuery(
            text = "image",
            rootUri = "file:///home",
            mimeFilter = "image/",
            recursive = true,
            includeHidden = false,
            maxDepth = 3,
            contentSearch = true,
            modifiedAfter = 1000L,
            modifiedBefore = 2000L,
            minSize = 100L,
            maxSize = 5000L,
            starredOnly = true
        )
        assertEquals("image/", query.mimeFilter)
        assertEquals(3, query.maxDepth)
        assertTrue(query.contentSearch)
        assertTrue(query.starredOnly)
    }
}
