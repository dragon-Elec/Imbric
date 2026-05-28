package com.imbric.core.ifs.backends

import kotlin.coroutines.AbstractCoroutineContextElement
import kotlin.coroutines.CoroutineContext

/**
 * Lightweight pipeline timing tracer that rides through coroutine context.
 * 
 * Tracks the data-to-UI pipeline by recording timestamps at each stage.
 * Zero coupling — no function signature changes. Each layer just calls:
 * ```
 * PipelineTimer.current?.mark("stage_name")
 * ```
 * 
 * Usage from UI layer:
 * ```
 * val timer = PipelineTimer("navigateTo")
 * withContext(timer.asContextElement()) {
 *     // ... entire pipeline runs, stages auto-record ...
 * }
 * timer.report()  // prints full breakdown
 * ```
 * 
 * Connectable to tests, UI, or CLI consumers.
 */
class PipelineTimer(private val label: String) {
    private val startNanos = System.nanoTime()
    private val marks = mutableListOf<Mark>()

    data class Mark(
        val stage: String,
        val elapsedMs: Long,
        val itemCount: Int? = null,
        val detail: String? = null
    )

    /** Record a timing mark at this instant. */
    fun mark(stage: String, itemCount: Int? = null, detail: String? = null) {
        val elapsed = (System.nanoTime() - startNanos) / 1_000_000
        marks.add(Mark(stage, elapsed, itemCount, detail))
    }

    /** Get all recorded marks (for programmatic access in tests). */
    fun getMarks(): List<Mark> = marks.toList()

    /** Get total elapsed time since creation. */
    fun totalMs(): Long = (System.nanoTime() - startNanos) / 1_000_000

    /** Get elapsed time between two stages (or from start to stage). */
    fun elapsedBetween(from: String?, to: String): Long {
        val fromMs = if (from == null) 0L else marks.find { it.stage == from }?.elapsedMs ?: 0L
        val toMs = marks.find { it.stage == to }?.elapsedMs ?: totalMs()
        return toMs - fromMs
    }

    /** Print full timing report to stdout. */
    fun report() {
        if (marks.isEmpty()) return
        val total = totalMs()
        val parts = marks.joinToString(" → ") { m ->
            val count = if (m.itemCount != null) " [${m.itemCount}]" else ""
            val detail = if (m.detail != null) " (${m.detail})" else ""
            "${m.stage}=+${m.elapsedMs}ms$count$detail"
        }
        println("[PIPELINE] $label: ${total}ms ($parts)")
    }

    // --- CoroutineContext integration ---

    private class Element(val timer: PipelineTimer) : AbstractCoroutineContextElement(Key) {
        companion object Key : CoroutineContext.Key<Element>
    }

    /** Returns a [CoroutineContext.Element] that carries this timer through coroutine scopes. */
    fun asContextElement(): CoroutineContext.Element = Element(this)

    companion object {
        /** Access the current pipeline timer from within a coroutine (returns null if none attached). */
        suspend fun current(): PipelineTimer? = kotlin.coroutines.coroutineContext[Element]?.timer
    }
}
