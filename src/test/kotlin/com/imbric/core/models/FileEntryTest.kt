package com.imbric.core.models

import kotlin.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class FileEntryTest {

    private fun entry(
        name: String,
        uri: String,
        modifiedTime: Instant?,
        isDirectory: Boolean = false
    ) = ListingFile(
        name = name,
        uri = uri,
        path = uri,
        isDirectory = isDirectory,
        pathType = PathType.PHYSICAL,
        size = 1L,
        mimeType = "text/plain",
        modifiedTime = modifiedTime
    )

    @Test
    fun `SortByDate orders newest first with folders on top`() {
        val dir = ListingDirectory()
        dir.add(entry("old", "file:///old", Instant.fromEpochSeconds(100)))
        dir.add(entry("folder", "file:///folder", Instant.fromEpochSeconds(300), isDirectory = true))
        dir.add(entry("new", "file:///new", Instant.fromEpochSeconds(200)))
        dir.sortWith(FileEntry.SortByDate)
        val names = (0 until dir.size).map { dir.get(it).name }
        assertEquals(listOf("folder", "new", "old"), names)
    }

    @Test
    fun `sub-second mtime survives the SoA round-trip at millis precision`() {
        // ListingDirectory stores epoch millis (its contract); the
        // row must read back exactly that truncation — no drift,
        // no null.
        val dir = ListingDirectory()
        val instant = Instant.fromEpochSeconds(100, 123_456_789)
        dir.add(entry("sub", "file:///sub", instant))
        val read = dir.get(0).modifiedTime
        assertEquals(Instant.fromEpochMilliseconds(instant.toEpochMilliseconds()), read)
    }

    @Test
    fun `glob compile is single-flight under concurrency`() {
        // Round 1: one pattern, 16 threads, repeated — every
        // thread must observe the identical (===) compiled
        // instance. Identity, not equals(): separate compile
        // runs produce separate Regex objects, so a shared
        // instance proves a single compile won the cache.
        val pattern = "a*b?c[0-9]*.txt"
        val threads = 16
        repeat(5) {
            val results = arrayOfNulls<Regex>(threads)
            val start = CountDownLatch(1)
            val done = CountDownLatch(threads)
            repeat(threads) { i ->
                Thread {
                    start.await()
                    results[i] = FileEntry.compileGlob(pattern)
                    done.countDown()
                }.apply { start() }
            }
            start.countDown()
            assertTrue(done.await(10, TimeUnit.SECONDS), "hammer threads must finish")
            val first = results[0]
            assertNotNull(first)
            assertTrue(
                results.all { it === first },
                "all threads must observe the identical Regex instance"
            )
        }

        // Round 2: 64 distinct patterns, two threads each —
        // per-pattern identity must hold for every pattern.
        val patterns = List(64) { "hammer_$it*.kt" }
        val firsts = arrayOfNulls<Regex>(patterns.size)
        val seconds = arrayOfNulls<Regex>(patterns.size)
        val start = CountDownLatch(1)
        val done = CountDownLatch(patterns.size * 2)
        patterns.forEachIndexed { i, p ->
            Thread {
                start.await()
                firsts[i] = FileEntry.compileGlob(p)
                done.countDown()
            }.apply { start() }
            Thread {
                start.await()
                seconds[i] = FileEntry.compileGlob(p)
                done.countDown()
            }.apply { start() }
        }
        start.countDown()
        assertTrue(done.await(30, TimeUnit.SECONDS), "64-pattern hammer threads must finish")
        patterns.forEachIndexed { i, p ->
            assertNotNull(firsts[i], "first compile of $p")
            assertNotNull(seconds[i], "second compile of $p")
            assertTrue(
                firsts[i] === seconds[i],
                "pattern $p must compile exactly once"
            )
        }
    }

    @Test
    fun `glob cache evicts the eldest entry at the 64-pattern cap`() {
        // Fill the cache with known patterns so foreign entries
        // compiled by earlier tests are evicted first, then push
        // one past the cap: the eldest known pattern must be
        // evicted and recompiled as a fresh instance.
        val victim = FileEntry.compileGlob("victim_z*")
        for (i in 0 until 64) {
            FileEntry.compileGlob("filler_$i*")
        }
        FileEntry.compileGlob("overflow_*")
        val recompiled = FileEntry.compileGlob("victim_z*")
        assertTrue(
            recompiled !== victim,
            "eldest pattern must be evicted at the 64-entry cap"
        )
    }
}
