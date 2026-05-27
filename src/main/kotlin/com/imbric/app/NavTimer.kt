package com.imbric.app

/**
 * Lightweight navigation timing logger.
 * Tracks the data-to-UI pipeline by marking timestamps at key stages.
 * Outputs a single line with all timings when [log] is called.
 *
 * Usage:
 * ```
 * val timer = NavTimer("navigateTo")
 * timer.mark("vm")           // ViewModel received the request
 * timer.mark("list_start")   // GIO listing started
 * timer.mark("list_end", 22) // GIO listing done (22 items)
 * timer.log("ui_ready")      // Final report
 * ```
 */
class NavTimer(private val label: String) {
    private val startNanos = System.nanoTime()
    private val marks = mutableListOf<Mark>()

    private data class Mark(val name: String, val elapsedMs: Long, val itemCount: Int? = null, val uri: String? = null)

    /** Record a timing mark at this instant. */
    fun mark(name: String, itemCount: Int? = null, uri: String? = null) {
        val elapsed = (System.nanoTime() - startNanos) / 1_000_000
        marks.add(Mark(name, elapsed, itemCount, uri))
    }

    /** Log the full timing trace to stdout. */
    fun log(finalMark: String? = null) {
        if (finalMark != null) mark(finalMark)
        if (marks.isEmpty()) return
        val totalMs = marks.last().elapsedMs
        val parts = marks.joinToString(" → ") { m ->
            val count = if (m.itemCount != null) " [${m.itemCount} items]" else ""
            val uriTag = if (m.uri != null) " <${m.uri}>" else ""
            "${m.name}=+${m.elapsedMs}ms$count$uriTag"
        }
        println("[NAV] $label: ${totalMs}ms ($parts)")
    }

    companion object {
        @Volatile
        private var globalRefNs: Long = 0L

        /** Record a render event using the global reference timestamp. */
        fun record(label: String) {
            val ref = globalRefNs
            if (ref > 0L) {
                val elapsed = (System.nanoTime() - ref) / 1_000_000
                println("[NAV-RENDER] $label: +${elapsed}ms")
            }
        }

        /** Set the global timing reference to now. */
        fun setRef() { globalRefNs = System.nanoTime() }
    }
}
