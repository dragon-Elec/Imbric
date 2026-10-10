@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class, kotlinx.coroutines.ExperimentalCoroutinesApi::class)

package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.logic.XferArbiter
import com.imbric.core.testing.InMemoryBackend
import com.imbric.core.transactions.models.TransactionEvent
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.uuid.Uuid

/**
 * Regression tests for the P0 fixed today: a dispatched job that can never run
 * ([TransactionDispatcher] finds no backend for its scheme) reported no status at all.
 * `Transaction.finishedOps` therefore never reached `totalOps`,
 * `TransactionEvent.Finished` was never emitted, and the transaction — plus every waiter on
 * it (TransferOrchestrator's collector, UndoManager's undo/redo) — parked forever while
 * retaining the op list.
 *
 * [TransactionDispatcher.reportUnrouteable] now reports FAILED through the same call shape as
 * the real failure path. These tests pin the resulting terminal contract:
 * unrouteable op → FAILED → transaction resolves to PARTIAL → `Finished` is emitted.
 *
 * Determinism: the manager, the dispatcher and the collectors all run on the injected test
 * scope, `advanceUntilIdle()` drains every queued job, and the wait for the terminal event
 * is bounded by [TERMINAL_TIMEOUT_MS] in *virtual* time — a missing event fails the test
 * immediately instead of hanging.
 *
 * The "no backend" precondition is expressed by a registry that has a working `memory`
 * backend registered: routing to `nosuchscheme:///` fails on scheme lookup, not because the
 * registry happens to be empty.
 */
class TransactionDispatcherTerminalStatusTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var registry: BackendRegistry

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend("memory")
        registry = BackendRegistry()
        registry.register("memory", backend)
    }

    @Test
    fun `an unrouteable operation finishes the transaction as PARTIAL`() = runTest {
        val dispatcher = TransactionDispatcher(registry, this)
        val manager = TransactionManager(registry, XferArbiter, dispatcher, this)

        val src = "nosuchscheme:///x"
        assertNull(registry.get(src), "precondition: no backend may claim $src")

        val jobId = Uuid.random()
        val tid = manager.startTransaction("Copy from an unregistered scheme")
        manager.addOperation(tid, "copy", src, "memory:///dest/x", jobId = jobId)

        val finished = armedFinished(manager, tid)
        manager.commitTransaction(tid)
        advanceUntilIdle()

        val event = withTimeoutOrNull(TERMINAL_TIMEOUT_MS) { finished.await() }
        assertNotNull(
            event,
            "no Finished event: the unrouteable job never reported a terminal status, so the transaction parks forever"
        )
        assertEquals(TransactionStatus.PARTIAL, event.status, "the single op FAILED, so the tx is PARTIAL")

        val op = manager.findOperation(tid, jobId)
        assertNotNull(op, "the failed op must still be recorded on the transaction")
        assertEquals(TransactionStatus.FAILED, op.status)
        assertTrue(
            op.error.contains("No backend registered"),
            "the failure must explain why the job could not run, was: '${op.error}'"
        )
    }

    @Test
    fun `an empty transaction finishes synchronously without dispatching a job`() = runTest {
        val dispatcher = TransactionDispatcher(registry, this)
        val manager = TransactionManager(registry, XferArbiter, dispatcher, this)

        val tid = manager.startTransaction("Nothing to do")
        val finished = armedFinished(manager, tid)

        // No ops: commitTransaction emits Finished inline, before it returns. A collector that
        // was not already armed misses it forever — this is the replay-0 trap the undo tests
        // guard against, and the reason undo() can never park on an empty transaction (its
        // undoOps would be empty and it returns before launching a waiter).
        manager.commitTransaction(tid)
        advanceUntilIdle()

        val event = withTimeoutOrNull(TERMINAL_TIMEOUT_MS) { finished.await() }
        assertNotNull(event, "an empty transaction must still reach a terminal event")
        assertEquals(TransactionStatus.COMPLETED, event.status)
    }

    @Test
    fun `one unrouteable operation does not strand the rest of the transaction`() = runTest {
        val dispatcher = TransactionDispatcher(registry, this)
        val manager = TransactionManager(registry, XferArbiter, dispatcher, this)

        backend.createFolder("memory:///", "src")
        backend.createFolder("memory:///", "dest")
        backend.createFile("memory:///src", "a.txt")

        val goodJobId = Uuid.random()
        val badJobId = Uuid.random()
        val tid = manager.startTransaction("Mixed copy")
        manager.addOperation(tid, "copy", "memory:///src/a.txt", "memory:///dest/a.txt", jobId = goodJobId)
        manager.addOperation(tid, "copy", "nosuchscheme:///x", "memory:///dest/x", jobId = badJobId)

        val finished = armedFinished(manager, tid)
        manager.commitTransaction(tid)
        advanceUntilIdle()

        val event = withTimeoutOrNull(TERMINAL_TIMEOUT_MS) { finished.await() }
        assertNotNull(event, "the transaction parked because finishedOps never reached totalOps")
        assertEquals(TransactionStatus.PARTIAL, event.status)

        // The routeable sibling still ran: a FAILED op must not cancel its neighbours, and the
        // terminal status is only decided once *every* op is terminal.
        assertTrue(backend.exists("memory:///dest/a.txt"), "the routeable op must still complete")
        assertEquals(TransactionStatus.COMPLETED, manager.findOperation(tid, goodJobId)?.status)
        assertEquals(TransactionStatus.FAILED, manager.findOperation(tid, badJobId)?.status)
        assertNull(registry.get("nosuchscheme:///x"), "sanity: still no backend for the bad scheme")
    }

    // --- helpers ---

    /**
     * Subscribes to the transaction's terminal event *before* the commit, because `events`
     * has replay = 0 and any emission made before a subscription exists is dropped forever.
     */
    private fun CoroutineScope.armedFinished(
        manager: TransactionManager,
        tid: Uuid
    ): Deferred<TransactionEvent.Finished> = async(start = CoroutineStart.UNDISPATCHED) {
        manager.events
            .filter { it.tid == tid }
            .filterIsInstance<TransactionEvent.Finished>()
            .first()
    }

    private companion object {
        /** Virtual-time budget for the terminal event; fails fast instead of hanging. */
        const val TERMINAL_TIMEOUT_MS = 5_000L
    }
}
