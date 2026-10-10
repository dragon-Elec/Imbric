package com.imbric.core.ifs.directories

import com.imbric.core.ifs.backends.gio.support.PipelineTimer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.lang.management.ManagementFactory
import java.util.Locale

/**
 * Measures the JVM process's CPU consumption *while nothing is happening* and records it
 * as a [PipelineTimer] mark.
 *
 * WHY THIS EXISTS
 * Idle CPU used to be eyeballed in `top`/`htop`, which cannot attribute the burn to a
 * subsystem. The bug class it is meant to catch is concrete and has shipped here before:
 * an animation scheduling frames forever on a pane that is no longer visible. There is no
 * proof either way — the listing looks right, the CPU is gone. A mark in the same trace as
 * the navigation that caused it turns "I think it went idle" into "here is what the process
 * was doing 2s after the frame settled".
 *
 * SCOPE — DEV TELEMETRY ONLY, NEVER AN ASSERTION INPUT
 * `processCpuLoad` is JVM-wide (every pane, every backend, the Compose runtime itself), not
 * scoped to the [DirState] that owns this sampler, and a mark lands in a trace that is
 * printed and thrown away. Nothing here feeds a test verdict, a threshold, or a control
 * flow decision about correctness. Treat a non-zero `idle_cpu_pct` as "go and look", never
 * as "this is broken".
 *
 * COST
 * The loop only exists when a [PipelineTimer] was supplied. Production never supplies one
 * (MainWindow builds a fresh timer per navigation and nulls it on report), so `start`
 * returns `null` without launching anything — the load path pays a single null check.
 * Once running, the loop holds a coroutine and reads one MXBean attribute every
 * [SAMPLE_INTERVAL_MS]. The [onSample] callback is the only per-sample allocation the
 * caller can add; the mark itself allocates one `Mark`.
 */
class IdleCpuSampler(
    /** Null in production: no tracing, no sampler. See [start]. */
    private val timer: PipelineTimer?,
    /** True once the owning DirState has been destroyed. Never mark after this is true. */
    private val isDestroyed: () -> Boolean,
    /**
     * False as soon as the owning DirState stops being idle — a new load claimed a fresh
     * epoch. Checked at the top of every iteration.
     */
    private val isStillIdle: () -> Boolean,
    /** Optional observer for the raw 0.0–1.0 load. Defaults to a no-op. */
    private val onSample: (Float) -> Unit = {}
) {
    /**
     * Launches the sampling loop on [scope] — the caller's existing scope, never a new
     * one, so [DirState.destroy]'s scope cancellation is also this loop's death.
     *
     * Settles for [IDLE_SETTLE_MS] first (the last frame has to land and the transient
     * allocations of the load have to be collected before "idle" means anything), then
     * samples every [SAMPLE_INTERVAL_MS] while still idle.
     *
     * Returns the loop's [Job], or `null` when there is no timer to feed. The loop ends —
     * without a final mark — on any of: scope cancellation, [isDestroyed] becoming true, or
     * [isStillIdle] becoming false. A destroyed instance can never be marked on, which is
     * the stuck-timer failure mode.
     */
    fun start(scope: CoroutineScope): Job? {
        val target = timer ?: return null
        return scope.launch {
            delay(IDLE_SETTLE_MS)
            while (true) {
                // Destroyed → stop silently. No longer idle (a new load claimed an epoch)
                // → stop silently. Either way the last thing this loop does is NOT a mark.
                if (isDestroyed() || !isStillIdle()) return@launch
                val load = readProcessCpuLoad()
                if (load != null) {
                    target.mark(
                        IDLE_MARK_STAGE,
                        itemCount = percentOf(load),
                        detail = formatPct(load)
                    )
                    onSample(load)
                }
                // A negative load means the platform declined to report (see
                // readProcessCpuLoad) — skip this tick, keep sampling. Nothing to record.
                delay(SAMPLE_INTERVAL_MS)
            }
        }
    }

    companion object {
        /** Quiet period after the last emission before the first sample is taken. */
        const val IDLE_SETTLE_MS = 2_000L

        /** Period between samples once the process is settled. */
        const val SAMPLE_INTERVAL_MS = 5_000L

        /** Mark stage name. Reported as `idle_cpu_pct=<n>[percent]`. */
        const val IDLE_MARK_STAGE = "idle_cpu_pct"

        /**
         * The JVM-wide CPU load bean, or null if this runtime declined to provide it.
         * Resolved once: the platform MXBean is a singleton and the lookup allocates.
         */
        private val osBean: com.sun.management.OperatingSystemMXBean? = try {
            ManagementFactory.getPlatformMXBean(com.sun.management.OperatingSystemMXBean::class.java)
        } catch (_: Throwable) {
            null
        }

        /**
         * Current process CPU load in 0.0–1.0, or null when unavailable.
         *
         * The Javadoc contract for `getProcessCpuLoad()` is "a negative value will be
         * returned if this information is not available" — in practice -1.0 on JVMs or
         * containers where the OS will not report it, and occasionally on the very first
         * call after startup before the first sampling window has elapsed. A negative
         * reading is therefore an absence, not a measurement: it is mapped to null and the
         * caller skips the tick. It must never be clamped to 0.0, which would report a
         * believable-looking "0% idle" for a sample that was never taken.
         */
        internal fun readProcessCpuLoad(): Float? {
            val load = try {
                osBean?.processCpuLoad ?: return null
            } catch (_: UnsupportedOperationException) {
                // Some containers hand back a proxy bean that refuses the read rather than
                // reporting -1. Same meaning: unavailable. try/catch costs nothing when it
                // does not throw.
                return null
            }
            return if (load < 0.0) null else load.toFloat()
        }

        /** Whole-number percent, carried in `itemCount` so the number is machine-readable. */
        private fun percentOf(load: Float): Int = (load * 100f).toInt()

        /** Human-readable percent for the mark's `detail`, e.g. `"3.42%"`. */
        private fun formatPct(load: Float): String =
            String.format(Locale.ROOT, "%.2f%%", load * 100f)
    }
}