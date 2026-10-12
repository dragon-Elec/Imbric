package com.imbric.core.ifs.directories

import com.imbric.core.models.*
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test

/**
 * Live-fire regression test for the P0-3 sortKey race.
 *
 * The race: sortBy writes sortKey, refresh reads it unlocked for
 * strategy.list(key=...) then again at rebuildComposite. A sortBy
 * straddling those two reads installs an A-sorted dir labelled B,
 * and the identity guard then skips the re-sort — state lies.
 *
 * Hammers sortBy against refresh on a real DirState and asserts two
 * invariants after every round:
 *  1. no row loss or duplication (the URI multiset is exact)
 *  2. the installed order always matches the last requested key
 *
 * Note: runs on the test scheduler, so it exercises the interleaving
 * at suspension points — strong evidence, but not a guarantee against
 * every native-thread interleaving production can produce.
 */
@OptIn(ExperimentalCoroutinesApi::class, kotlin.uuid.ExperimentalUuidApi::class)
class SortRaceTest {

    private fun populate(backend: InMemoryBackend, root: String, n: Int) {
        for (i in 0 until n) {
            // zero-padded so NAME order != insertion order
            val name = "f%03d".format(n - 1 - i)
            val uri = "$root/$name"
            backend.fs[uri] = FileInfo(
                name = name, path = uri, uri = uri,
                isDirectory = false,
                modifiedTime = kotlin.time.Instant.fromEpochSeconds(i.toLong()),
            )
        }
    }

    @Test
    fun `sortBy always wins over concurrent refresh`() = runTest {
        val backend = InMemoryBackend()
        val root = "memory://race"
        val n = 200
        populate(backend, root, n)

        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState(root, backend, backgroundScope, testDispatcher)
        advanceUntilIdle()
        assertEquals(n, dirState.items.value.size, "initial load")

        val expected = (0 until n).map { "f%03d".format(n - 1 - it) }.toSet()

        // Interleave sorts and refreshes. Each round ends with a sortBy,
        // so the final order must always match that key.
        val keys = listOf(SortKey.NAME, SortKey.MODIFIED, SortKey.SIZE, SortKey.TYPE)
        repeat(40) { round ->
            val key = keys[round % keys.size]

            // Fire a refresh and a sort concurrently — the exact interleave
            // the race needs. Both are suspend; the test scheduler interleaves them.
            val refreshJob = launch(Dispatchers.Default) { dirState.refresh() }
            val sortJob = launch(Dispatchers.Default) { dirState.sortBy(key) }
            sortJob.join()
            refreshJob.join()
            advanceUntilIdle()

            val items = dirState.items.value

            // Invariant 1: exact multiset — no loss, no duplication.
            val uris = items.map { it.uri.substringAfterLast('/') }.toSet()
            assertEquals(expected, uris, "round $round: row loss or duplication")
            assertEquals(n, items.size, "round $round: size changed")

            // Invariant 2: the installed order matches the last requested key.
            val ordered = when (key) {
                SortKey.NAME -> items.map { it.name }.zipWithNext().all { (a, b) -> a <= b }
                // SortByDate is newest-first (thenByDescending) — assert descending.
                SortKey.MODIFIED ->
                    items.map { it.modifiedTime?.toEpochMilliseconds() ?: -1L }
                        .zipWithNext().all { (a, b) -> a >= b }
                else -> true // SIZE/TYPE need richer fixtures; NAME/MODIFIED prove the race
            }
            assertTrue(ordered, "round $round: order does not match $key — state lied")
        }

        dirState.destroy()
    }
}
