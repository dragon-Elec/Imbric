@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class, kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.XferArbiter
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

/**
 * TEMPORARY live-fire probe for the P0-1 fix (deleted after verification).
 * Wedges the terminal-event subscriber forever, overfills the 128-slot buffer
 * with 70 empty commits, and asserts: (1) status truth still resolves via
 * getStatus, (2) the suspending-fallback emits complete (bounded 5s) instead
 * of parking forever — i.e. no lingerers on the manager scope.
 */
class TerminalFallbackFireTest {

    @Test
    fun `fallback emit is bounded under wedged subscriber`() = runTest {
        val backend = InMemoryBackend("memory")
        val registry = BackendRegistry()
        registry.register("memory", backend)
        val dispatcher = TransactionDispatcher(registry, this)
        val manager = TransactionManager(registry, XferArbiter, dispatcher, this)

        // Wedge FIRST (UNDISPATCHED subscribes synchronously): takes the first
        // event then parks forever with no timer, so the buffer fills and every
        // later terminal is forced onto the scope.launch fallback path.
        backgroundScope.launch(start = CoroutineStart.UNDISPATCHED) {
            manager.events.collect { awaitCancellation() }
        }

        var lastTid: Uuid = Uuid.random()
        repeat(70) { i ->
            lastTid = manager.startTransaction("probe-t$i")
            manager.commitTransaction(lastTid)
        }
        advanceUntilIdle()

        assertEquals(
            TransactionStatus.COMPLETED, manager.getStatus(lastTid),
            "status truth must resolve even when terminal delivery wedges"
        )
        val lingering = coroutineContext[Job]?.children?.toList().orEmpty()
        assertTrue(
            lingering.isEmpty(),
            "fallback emits must complete (5s bound), found ${lingering.size} parked emitter(s)"
        )
    }
}
