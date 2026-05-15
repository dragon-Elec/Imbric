package com.imbric.core.ifs

import kotlin.math.max
import java.util.concurrent.ConcurrentHashMap

/**
 * Profiles backend latency via passive observation.
 * Backends feed timing data; consumers read the profile to make decisions.
 */
interface LatencyProfiler {
    fun recordSample(scheme: String, timeMs: Long)
    fun getLatency(scheme: String): LatencyProfile
}

/**
 * Rolling-average passive profiler with decay and fixed overrides.
 *
 * - Fixed overrides for known-bad schemes (MTP → HIGH, virtual → LOW).
 * - Decay mechanism: after 20 samples, halves the stored sum so old spikes
 *   don't permanently bias the average.
 */
class PassiveLatencyProfiler : LatencyProfiler {

    private val profiles = ConcurrentHashMap<String, MountProfile>()

    init {
        // Fixed overrides — these don't profile dynamically
        setFixed("mtp", LatencyProfile.HIGH)     // MTP devices are always slow
        setFixed("trash", LatencyProfile.LOW)    // virtual, in-memory metadata only
        setFixed("recent", LatencyProfile.LOW)   // virtual, GtkRecentManager cache
        setFixed("search", LatencyProfile.LOW)   // virtual, Tracker DB lookup
    }

    fun setFixed(scheme: String, profile: LatencyProfile) {
        profiles[scheme] = MountProfile(isProfileable = false, fixedLatency = profile)
    }

    override fun recordSample(scheme: String, timeMs: Long) {
        profiles.getOrPut(scheme) { MountProfile() }.recordSample(timeMs)
    }

    override fun getLatency(scheme: String): LatencyProfile {
        return profiles.getOrPut(scheme) { MountProfile() }.getCurrentLatency()
    }
}

/**
 * No-op profiler — returns LOW always, records nothing.
 * Used by test backends to avoid side effects.
 */
class NoopLatencyProfiler : LatencyProfiler {
    override fun recordSample(scheme: String, timeMs: Long) = Unit
    override fun getLatency(scheme: String): LatencyProfile = LatencyProfile.LOW
}

// ─── Internal: per-scheme rolling state ───────────────────────────────────

/**
 * Tracks a rolling average of latency samples for a single scheme.
 *
 * @param isProfileable  if false, [getCurrentLatency] always returns [fixedLatency]
 * @param fixedLatency   static value used when not profileable or before first sample
 */
class MountProfile(
    private val isProfileable: Boolean = true,
    private val fixedLatency: LatencyProfile = LatencyProfile.LOW
) {
    private var sampleCount = 0
    private var totalTimeMs = 0L

    @Synchronized
    fun recordSample(timeMs: Long) {
        if (!isProfileable) return
        sampleCount++
        totalTimeMs += timeMs

        // Decay: prevent old spikes from dominating permanently
        if (sampleCount > 20) {
            sampleCount /= 2
            totalTimeMs /= 2
        }
    }

    fun getCurrentLatency(): LatencyProfile {
        if (!isProfileable || sampleCount == 0) return fixedLatency
        val averageMs = totalTimeMs / max(1, sampleCount)
        return when {
            averageMs < 50  -> LatencyProfile.LOW
            averageMs < 300 -> LatencyProfile.MODERATE
            else            -> LatencyProfile.HIGH
        }
    }
}
