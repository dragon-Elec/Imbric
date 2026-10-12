@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.models

import com.imbric.core.ifs.directories.DirState
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlin.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals

@OptIn(ExperimentalCoroutinesApi::class, kotlin.uuid.ExperimentalUuidApi::class)
class EnrichedListingViewTest {

    private fun fileEntry(
        name: String,
        uri: String,
        modifiedTime: Instant = Instant.fromEpochSeconds(0)
    ) = FileInfo(
        name = name,
        uri = uri,
        path = uri,
        isDirectory = false,
        modifiedTime = modifiedTime
    )

    @Test
    fun `zero-delta view reads through base, delta view maps rows`() {
        // Mapping invariant: passthrough is active exactly
        // when the delta maps are all empty (mapping is null
        // in that branch), and the mapping branch is active
        // otherwise. Both branches must read correctly —
        // the reads previously used !! on the mapping.
        val base = ListingDirectory(8)
        base.add(fileEntry("a", "file:///a"))
        base.add(fileEntry("b", "file:///b"))

        // Zero deltas: passthrough branch — rows come
        // straight from the base, no mapping array built.
        val zeroDelta = EnrichedListingView(
            base = base,
            comparator = FileEntry.SortByName,
            additions = emptyMap(),
            deletions = emptySet(),
            enrichments = emptyMap()
        )
        assertEquals(2, zeroDelta.size)
        assertEquals("file:///a", zeroDelta[0].uri)
        assertEquals("file:///b", zeroDelta[1].uri)

        // Addition delta: mapping branch — the addition
        // row merges into its sorted position.
        val withAddition = EnrichedListingView(
            base = base,
            comparator = FileEntry.SortByName,
            additions = mapOf("file:///c" to fileEntry("c", "file:///c")),
            deletions = emptySet(),
            enrichments = emptyMap()
        )
        assertEquals(3, withAddition.size)
        assertEquals(
            listOf("file:///a", "file:///b", "file:///c"),
            (0 until withAddition.size).map { withAddition[it].uri }
        )

        // Deletion delta: mapping branch — the deleted row
        // is skipped.
        val withDeletion = EnrichedListingView(
            base = base,
            comparator = FileEntry.SortByName,
            additions = emptyMap(),
            deletions = setOf("file:///a"),
            enrichments = emptyMap()
        )
        assertEquals(1, withDeletion.size)
        assertEquals("file:///b", withDeletion[0].uri)

        // Enrichment-only delta: mapping branch — the
        // enriched overlay replaces the base row in place.
        val enriched = fileEntry("a", "file:///a").copy(
            attributes = mapOf("std::emblems" to listOf("emblem-readonly"))
        )
        val withEnrichment = EnrichedListingView(
            base = base,
            comparator = FileEntry.SortByName,
            additions = emptyMap(),
            deletions = emptySet(),
            enrichments = mapOf("file:///a" to enriched)
        )
        assertEquals(2, withEnrichment.size)
        val first = withEnrichment[0] as FileInfo
        assertEquals("file:///a", first.uri)
        assertEquals(listOf("emblem-readonly"), first.attributes["std::emblems"])
    }

    @Test
    fun `sortBy during an active view does not crash`() = runTest {
        // Accepted transient: the view holds the base by
        // reference while sortBy permutes it in place, so
        // rows are transiently reordered — but reading the
        // live view must never throw.
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        for (i in 1..10) backend.createFile("memory://dir", "file$i.txt")
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        val liveView = dirState.items.value
        dirState.sortBy(SortKey.MODIFIED)
        advanceUntilIdle()

        // Read the whole live view after the in-place
        // permutation — must not throw (size or index).
        repeat(liveView.size) { i -> liveView[i].uri }
        dirState.destroy()
    }

    @Test
    fun `one revision bump per refresh`() = runTest {
        // Revision counts composite emissions, so one
        // rebuild must publish exactly one new view.
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")
        val testDispatcher = UnconfinedTestDispatcher(testScheduler)
        val dirState = DirState("memory://dir", backend, backgroundScope, testDispatcher)
        advanceUntilIdle()

        val before = dirState.revision.value
        dirState.refresh()
        advanceUntilIdle()

        assertEquals(before + 1, dirState.revision.value)
        dirState.destroy()
    }

    @Test
    fun `revision bumps once per event-batch rebuild`() = runBlocking {
        // Real coroutines: the 200ms storm-catcher debounce
        // needs a real clock, so this test cannot use the
        // runTest virtual clock.
        val backend = InMemoryBackend()
        backend.createFolder("memory://", "dir")
        backend.createFile("memory://dir", "a.txt")
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val dirState = DirState("memory://dir", backend, scope, Dispatchers.Default)
            dirState.isLoading.first { !it }
            delay(50) // let the watcher coroutines start collecting

            val before = dirState.revision.value
            backend.emitFileEvent(com.imbric.core.ifs.FileEvent.Modified("memory://dir/a.txt"))
            delay(500) // 200ms debounce + fetch + rebuild

            // Exactly one composite emission for the batch.
            assertEquals(before + 1, dirState.revision.value)
            dirState.destroy()
        } finally {
            scope.cancel()
        }
    }
}
