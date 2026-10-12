@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.testing

import com.imbric.core.models.FileInfo
import com.imbric.core.models.VfsQuery
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlin.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals

class InMemoryBackendTest {

    @Test
    fun `null-mtime rows follow GIO zero-MAX bound asymmetry`() = runTest {
        // GIO's search treats a missing mtime as 0 for the
        // after-bound and MAX for the before-bound, so a
        // row with unknown time is excluded from any
        // finite time range. The in-memory backend must
        // match — its old 0L fallback on BOTH bounds
        // wrongly included null-mtime rows in before-
        // bounded queries.
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.fs["memory://dir/bottom.txt"] = FileInfo(
            path = "memory://dir/bottom.txt",
            uri = "memory://dir/bottom.txt",
            name = "bottom.txt",
            isDirectory = false,
            modifiedTime = null
        )
        backend.fs["memory://dir/stamped.txt"] = FileInfo(
            path = "memory://dir/stamped.txt",
            uri = "memory://dir/stamped.txt",
            name = "stamped.txt",
            isDirectory = false,
            modifiedTime = Instant.fromEpochMilliseconds(5000)
        )

        val unbounded = backend.search(VfsQuery(text = "", rootUri = "memory://dir"))
            .toList().flatten()
        assertEquals(2, unbounded.size, "unbounded search matches both rows")

        val after = backend.search(
            VfsQuery(text = "", rootUri = "memory://dir", modifiedAfter = 1000)
        ).toList().flatten()
        assertEquals(
            listOf("stamped.txt"), after.map { it.name },
            "null-mtime row is epoch-floor (0) for the after-bound"
        )

        val before = backend.search(
            VfsQuery(text = "", rootUri = "memory://dir", modifiedBefore = 6000)
        ).toList().flatten()
        assertEquals(
            listOf("stamped.txt"), before.map { it.name },
                "null-mtime row is MAX for the before-bound"
        )
    }
}
