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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Regression tests for the P0 fixed today: `TransactionManager.events` is a **replay-0**
 * [kotlinx.coroutines.flow.SharedFlow], so a waiter that subscribes *after* a transaction
 * has already emitted `TransactionEvent.Finished` misses it forever. UndoManager parked on
 * that wait with `busy` held true, which disables undo/redo for the rest of the session and
 * leaves a permanent "busy" spinner on the toolbar.
 *
 * UndoManager now arms an `UNDISPATCHED` collector *before* calling `commitTransaction` and
 * hands the value over through a CompletableDeferred, so the event is captured no matter how
 * fast the operation completes. These tests pin that contract down from the public API only
 * (`startTransaction` → `addOperation` → `commitTransaction` → `onHistoryCommitted` → `undo`).
 *
 * Determinism:
 * - UndoManager, TransactionManager and TransactionDispatcher all take an **injected** scope,
 *   so nothing here runs on Dispatchers.Default/IO and nothing outlives the test.
 * - Test 1 drives the test scheduler (virtual time) with `advanceUntilIdle()`. A parked undo
 *   would be driven into UndoManager's 60s `UNDO_TIMEOUT_MS` fallback and pushed back onto
 *   the undo stack, so `canRedo()` stays false and the assert fails — no hang, no wall clock.
 * - Test 2 runs the dispatcher on `Dispatchers.Unconfined`, which makes an InMemoryBackend
 *   rename complete *inline*, i.e. `Finished` is emitted inside `commitTransaction` before
 *   any after-the-fact subscription could possibly exist — the exact worst case. The wait
 *   for `canRedo()` is bounded by [TERMINAL_TIMEOUT_MS] so a regression fails in 5s instead
 *   of parking for the 60s production fallback.
 *
 * Why the worst case cannot be driven through `undo()` with an EMPTY op set: `commitTransaction`
 * emits `Finished` synchronously for an empty op list, but `undo()` filters the transaction
 * down to COMPLETED ops that carry an `UndoAction` and returns early (`undoOps.isEmpty()`)
 * without ever launching the waiter — so an empty transaction can never park. A NON-empty op
 * set whose op completes with no suspension point is the reachable version of the race, and
 * that is what [commitRename] reproduces.
 *
 * WHICH TEST IS THE RACE PIN (oracle review, 2026-10-10): the second test
 * (`undo does not park when the operation finishes synchronously during commit`, run on
 * `Dispatchers.Unconfined`) is the load-bearing regression test — emission happens truly
 * inline inside `commitTransaction`, so only the UNDISPATCHED pre-armed collector catches it.
 * The first test runs its dispatcher on the virtual-time test scheduler: even the OLD
 * subscribe-after-commit bug subscribed in time before `advanceUntilIdle()` ran the job,
 * so that test pins the happy path (undo completes, stacks rotate, file renamed back) but
 * would NOT have failed with the bug reintroduced. Keep both; only the second guards the race.
 */
class UndoManagerRaceTest {

    private lateinit var backend: InMemoryBackend
    private lateinit var registry: BackendRegistry

    @BeforeTest
    fun setup() {
        backend = InMemoryBackend("memory")
        registry = BackendRegistry()
        registry.register("memory", backend)
    }

    @Test
    fun `undo completes when the transaction finishes during commit`() = runTest {
        val dispatcher = TransactionDispatcher(registry, this)
        val manager = TransactionManager(registry, XferArbiter, dispatcher, this)
        val undoManager = UndoManager(registry, manager, this)
        undoManager.attach()

        commitRename(manager)
        assertTrue(undoManager.canUndo(), "the committed rename must land on the undo stack")
        assertEquals("Undo Rename", undoManager.getUndoLabel())

        assertTrue(undoManager.undo(), "undo() must accept the committed rename")

        // Drive the undo operation and its terminal event to completion. If `Finished` were
        // dropped, undo() would sit in withTimeoutOrNull(UNDO_TIMEOUT_MS) and busy would stay
        // true, leaving canUndo()/canRedo() false forever.
        advanceUntilIdle()

        assertTrue(undoManager.canRedo(), "undo must complete and hand the transaction to the redo stack")
        assertFalse(undoManager.canUndo(), "the undo stack is empty once the undo lands on redo")
        assertEquals("Redo Rename", undoManager.getRedoLabel())

        // The undo really ran: the file is back under its original name.
        assertFalse(backend.exists(RENAMED), "the renamed file must be gone after undo")
        assertTrue(backend.exists(SRC), "undo must restore the original name")
    }

    @Test
    fun `undo does not park when the operation finishes synchronously during commit`() {
        // Unconfined: the dispatcher's `scope.launch` runs the job body inline, so with an
        // InMemoryBackend op (no suspension points at all) `Finished` is emitted from inside
        // commitTransaction — before any collector subscribed after the call could exist.
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val dispatcher = TransactionDispatcher(registry, scope)
            val manager = TransactionManager(registry, XferArbiter, dispatcher, scope)
            val undoManager = UndoManager(registry, manager, scope)
            undoManager.attach()

            runBlocking {
                commitRename(manager)
                assertTrue(undoManager.canUndo())

                assertTrue(undoManager.undo())

                // Bounded wait: the undo transaction finishes synchronously, so this poll
                // returns immediately. With the regression it would spin until the 5s oracle
                // fires (production only gives up after 60s).
                withTimeout(TERMINAL_TIMEOUT_MS) {
                    while (!undoManager.canRedo()) delay(POLL_INTERVAL_MS)
                }

                assertFalse(undoManager.canUndo(), "busy must have cleared for undo to be unavailable")
                assertFalse(backend.exists(RENAMED))
                assertTrue(backend.exists(SRC))
            }
        } finally {
            scope.cancel()
        }
    }

    // --- helpers ---

    /**
     * Commits a real, reversible rename through the manager's public path and waits for its
     * terminal event. A rename is used because it is the one op whose `InMemoryBackend`
     * execution yields a non-null `UndoAction.RenameUndo` — `copy`/`move` in that backend
     * emit progress with a null inverse payload, which `undo()` filters out (empty undoOps).
     */
    private suspend fun CoroutineScope.commitRename(manager: TransactionManager) {
        backend.createFolder("memory:///", "dir")
        backend.createFile("memory:///dir", "report.txt")

        val tid = manager.startTransaction("Rename report.txt")
        // The dispatcher's rename op treats `dest` as the new *name*, not a URI.
        manager.addOperation(tid, "rename", SRC, "report-final.txt")

        val finished = armedFinished(manager, tid)
        manager.commitTransaction(tid)

        val event = withTimeoutOrNull(TERMINAL_TIMEOUT_MS) { finished.await() }
        assertNotNull(event, "the rename transaction never finished")
        assertEquals(TransactionStatus.COMPLETED, event.status)
        assertTrue(backend.exists(RENAMED), "the committed rename must have been applied")
    }

    /**
     * Subscribes before the transaction can finish. `UNDISPATCHED` so the subscription is live
     * the instant this returns — the fix under test, expressed the same way UndoManager does it.
     */
    private fun CoroutineScope.armedFinished(
        manager: TransactionManager,
        tid: kotlin.uuid.Uuid
    ): Deferred<TransactionEvent.Finished> = async(start = CoroutineStart.UNDISPATCHED) {
        manager.events
            .filter { it.tid == tid }
            .filterIsInstance<TransactionEvent.Finished>()
            .first()
    }

    private companion object {
        const val SRC = "memory:///dir/report.txt"
        const val RENAMED = "memory:///dir/report-final.txt"

        /** Oracle budget. Far above an in-memory op, far below the 60s production fallback. */
        const val TERMINAL_TIMEOUT_MS = 5_000L
        const val POLL_INTERVAL_MS = 10L
    }
}
