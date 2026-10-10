@file:OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package com.imbric.core.ifs.directories

import com.imbric.core.models.FileInfo
import com.imbric.core.testing.InMemoryBackend
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * Tab-lifecycle contract for [DirStateRegistry] — the part that used to be verified by
 * hand in an interactive multi-tab session.
 *
 * The invariants under test:
 * - a [DirStateRegistry.pin]ned URI is immune to LRU eviction (a visible tab can never
 *   blank out), and the LRU victim is the oldest *evictable* entry, not the oldest entry;
 * - eviction is access-ordered, not insertion-ordered;
 * - [DirStateRegistry.release] drops one viewer reference and destroys at refcount 0;
 * - destroy() runs *outside* the registry lock and after the victim is detached, so a
 *   teardown that re-enters the registry cannot observe a half-mutated LinkedHashMap.
 *
 * Pure JVM: an [InMemoryBackend] is handed to the registry as the fallback backend (the
 * "simple mode for tests" constructor), so no GIO/native call happens anywhere. DirState
 * runs its listing/enrichment workers on the shared listing thread pool; these tests
 * assert lifecycle state only and never wait on listing progress.
 */
class DirStateRegistryTest {

    private lateinit var backend: InMemoryBackend

    /** Registries created by [trackRegistry], cleared in [tearDown]. */
    private var tracked: DirStateRegistry? = null

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend("memory")
        // Real directories, so every DirState below lists actual content.
        for (n in 1..12) {
            val uri = uri(n)
            backend.fs[uri] = FileInfo(
                name = "dir$n", path = uri, uri = uri,
                displayName = "dir$n", isDirectory = true
            )
        }
    }

    @AfterTest
    fun tearDown() {
        tracked?.clear()
        tracked = null
    }

    // --- a. pinning blocks eviction ---

    @Test
    fun `pinned uri survives eviction and the oldest evictable entry is destroyed`() = runTest {
        val registry = trackRegistry(maxSize = 2)

        val a = registry.pin(uri(1))
        val b = registry.getOrCreate(uri(2))
        val c = registry.getOrCreate(uri(3))

        assertTrue(registry.isPinned(uri(1)), "a pinned viewer must be registered")
        assertTrue(registry.contains(uri(1)), "a pinned uri must stay cached")
        assertFalse(a.isDestroyedState, "a pinned DirState must never be evicted")
        assertSame(a, registry.getOrCreate(uri(1)), "the pinned instance must still be the cached one")

        // The third insert overflows maxSize=2. a is pinned, so b (the oldest evictable
        // entry) is the victim and a survives — the whole point of the pin model.
        assertTrue(b.isDestroyedState, "the oldest NON-pinned entry must be the eviction victim")
        assertFalse(registry.contains(uri(2)), "the victim must be detached from the cache")
        assertFalse(c.isDestroyedState, "the just-inserted entry must not be evicted")
        assertTrue(registry.contains(uri(3)))
        assertEquals(2, registry.size, "cache must be trimmed back to maxSize")

        // Overflow again: the pinned entry is skipped once more and c is taken next.
        registry.getOrCreate(uri(4))
        assertFalse(a.isDestroyedState, "the pinned entry must be skipped on every overflow")
        assertTrue(c.isDestroyedState, "the next-oldest evictable entry must be evicted")
        assertFalse(registry.contains(uri(3)))
        assertEquals(2, registry.size)
    }

    // --- b. unpin makes an entry evictable again ---

    @Test
    fun `unpin makes the uri evictable again`() = runTest {
        val registry = trackRegistry(maxSize = 2)

        val a = registry.pin(uri(1))
        registry.getOrCreate(uri(2))
        assertTrue(registry.isPinned(uri(1)))

        registry.unpin(uri(1))
        assertFalse(registry.isPinned(uri(1)), "unpin must drop the viewer reference")
        assertTrue(registry.contains(uri(1)), "unpin keeps the instance cached for instant return")

        val c = registry.getOrCreate(uri(3))
        assertTrue(a.isDestroyedState, "an unpinned uri is evictable again")
        assertFalse(registry.contains(uri(1)))
        assertTrue(registry.contains(uri(2)), "a newer unpinned entry must be preferred")
        assertTrue(registry.contains(uri(3)))
        assertFalse(c.isDestroyedState)
        assertEquals(2, registry.size)
    }

    // --- c. release destroys at refcount 0 ---

    @Test
    fun `release destroys the instance and drops it from the cache`() = runTest {
        val registry = trackRegistry()

        val b = registry.pin(uri(2))
        assertTrue(registry.isPinned(uri(2)))
        assertTrue(registry.contains(uri(2)))
        assertEquals(1, registry.size)

        registry.release(uri(2))

        assertFalse(registry.contains(uri(2)), "release must remove the entry from the cache")
        assertTrue(b.isDestroyedState, "release at refcount 0 must destroy immediately, not wait for the LRU")
        assertFalse(registry.isPinned(uri(2)))
        assertEquals(0, registry.size)

        // Releasing an already-released (unknown) uri is a no-op, not a crash.
        registry.release(uri(2))
        assertEquals(0, registry.size)
    }

    // --- d. shared uri across viewers is refcounted ---

    @Test
    fun `a shared uri survives until the last viewer releases it`() = runTest {
        val registry = trackRegistry()

        // Two viewers opened on the same URI: same instance, refcount 2.
        val first = registry.pin(uri(3))
        val second = registry.pin(uri(3))
        assertSame(first, second, "both viewers must share one DirState")
        assertEquals(1, registry.size, "a shared uri is a single cache entry")

        registry.release(uri(3))

        assertTrue(registry.contains(uri(3)), "the surviving viewer keeps the instance alive")
        assertFalse(first.isDestroyedState, "release must not destroy while another viewer holds it")
        assertTrue(registry.isPinned(uri(3)), "refcount is still 1")
        assertEquals(1, registry.size)
        assertSame(first, second, "the shared instance is unchanged")

        registry.release(uri(3))

        assertFalse(registry.contains(uri(3)))
        assertTrue(second.isDestroyedState, "the last release must destroy the shared instance")
        assertFalse(registry.isPinned(uri(3)))
        assertEquals(0, registry.size)
    }

    // --- e. the victim is least-recently-used, not oldest-inserted ---

    @Test
    fun `eviction picks the least recently used entry not the oldest inserted`() = runTest {
        val registry = trackRegistry(maxSize = 2)

        val a = registry.getOrCreate(uri(1))
        val b = registry.getOrCreate(uri(2))
        // Touch a: it becomes the most-recently-used entry even though b was inserted later.
        assertSame(a, registry.getOrCreate(uri(1)))

        val c = registry.getOrCreate(uri(3))

        assertTrue(
            b.isDestroyedState,
            "the LRU victim is b (least recently used); an insertion-ordered cache would evict a"
        )
        assertFalse(a.isDestroyedState, "the recently used entry must survive")
        assertFalse(c.isDestroyedState)
        assertTrue(registry.contains(uri(1)))
        assertFalse(registry.contains(uri(2)))
        assertTrue(registry.contains(uri(3)))
        assertEquals(2, registry.size)
    }

    // --- f. structural: repeated overflow stays bounded, and every victim is destroyed ---

    @Test
    fun `repeated overflow keeps the cache bounded and destroys every victim`() = runTest {
        // maxSize = 1 forces a single-eviction on every insert past the first, so the
        // detach-then-destroy path runs on every call and a corrupted LinkedHashMap
        // (destroying a victim still attached to the cache, or dropping the new entry)
        // shows up as a wrong size or a leaked live instance.
        val registry = trackRegistry(maxSize = 1)

        val states = (1..5).map { registry.getOrCreate(uri(it)) }

        assertEquals(1, registry.size, "cache must never exceed maxSize")
        assertTrue(registry.contains(uri(5)))
        assertFalse(states.last().isDestroyedState, "the newest entry stays alive")
        states.dropLast(1).forEachIndexed { i, victim ->
            assertTrue(victim.isDestroyedState, "victim ${i + 1} must have been destroyed")
        }
        assertEquals(4, states.count { it.isDestroyedState })
    }

    @Test
    fun `concurrent pin release churn never corrupts the cache`() {
        val churnBackend = InMemoryBackend("memory")
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val registry = DirStateRegistry(churnBackend, scope, maxSize = 4)
            val uris = (1..12).map { uri(it) }

            val threads = 4
            val opsPerThread = 100
            val start = CountDownLatch(1)
            val done = CountDownLatch(threads)
            val failures = CopyOnWriteArrayList<Throwable>()
            val pool = Executors.newFixedThreadPool(threads)

            repeat(threads) { t ->
                pool.execute {
                    try {
                        start.await()
                        repeat(opsPerThread) { i ->
                            val target = uris[(t * opsPerThread + i) % uris.size]
                            when ((i + t) % 4) {
                                0 -> registry.pin(target)
                                1 -> registry.getOrCreate(target)
                                2 -> registry.unpin(target)
                                else -> registry.release(target)
                            }
                        }
                    } catch (e: Throwable) {
                        failures.add(e)
                    } finally {
                        done.countDown()
                    }
                }
            }

            start.countDown()
            val finished = done.await(CHURN_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            pool.shutdownNow()
            assertTrue(finished, "churn threads did not finish within ${CHURN_TIMEOUT_SECONDS}s")
            assertTrue(failures.isEmpty(), "concurrent registry access threw: ${failures.firstOrNull()}")

            // No uri may ever resolve to two instances, and nothing served may be dead.
            uris.forEach { target ->
                val state = registry.getOrCreate(target)
                assertSame(state, registry.getOrCreate(target), "two instances served for $target")
                assertFalse(state.isDestroyedState, "$target resolved to a destroyed instance")
            }

            // A destroyed DirState must never stay attached to the cache (destroy runs on
            // detached victims only), and the cache is keyed by uri so it can never exceed
            // the distinct uri count.
            val cached = uris.count { registry.contains(it) }
            assertEquals(cached, registry.size, "the cache holds entries that are not alive")
            assertTrue(registry.size <= uris.size, "cache (${registry.size}) exceeded ${uris.size} distinct uris")

            // Whatever survives the churn, a pinned viewer's own instance is never destroyed.
            uris.filter { registry.isPinned(it) }.forEach { target ->
                assertFalse(registry.getOrCreate(target).isDestroyedState, "pinned $target was destroyed")
            }
        } finally {
            scope.cancel()
        }
    }

    // --- helpers ---

    private fun uri(n: Int): String = "memory:///dir$n"

    /** Creates a registry on the test's [TestScope.backgroundScope] and registers it for cleanup. */
    private fun TestScope.trackRegistry(maxSize: Int = DirStateRegistry.DEFAULT_MAX_SIZE): DirStateRegistry {
        val registry = DirStateRegistry(backend, backgroundScope, maxSize = maxSize)
        tracked = registry
        return registry
    }

    private companion object {
        const val CHURN_TIMEOUT_SECONDS = 30L
    }
}
