package com.imbric.core.ifs

enum class Locality {
    LOCAL,
    NETWORK,
    VIRTUAL
}

/**
 * Dynamic latency classification based on rolling-average observation.
 * - LOW:      < 50ms average   (local SSD, fast NAS)
 * - MODERATE: 50–300ms average (spinning disk, typical network)
 * - HIGH:     > 300ms average  (MTP, slow VPN, congested link)
 */
enum class LatencyProfile {
    LOW,
    MODERATE,
    HIGH
}

data class BackendCapabilities(
    val locality: Locality = Locality.LOCAL,
    /** Rolling average of observed operation latency. */
    val latencyProfile: LatencyProfile = LatencyProfile.LOW,
    val supportsBatch: Boolean = true,
    val supportsSearch: Boolean = false,
    val supportsTrash: Boolean = true,
    val supportsSymlinks: Boolean = true,
    val reliableMtime: Boolean = true,
    val reliableSize: Boolean = true,
    val caseSensitive: Boolean = true
)
