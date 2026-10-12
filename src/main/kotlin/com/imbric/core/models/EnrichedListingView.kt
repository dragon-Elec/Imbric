package com.imbric.core.models

/**
 * Immutable composite view that merges an [ListingDirectory] snapshot with a delta layer.
 *
 * - **additions**: new/modified files from file events (not in the base snapshot)
 * - **deletions**: URIs of files that have been removed
 * - **enrichments**: files enriched with metadata (emblems, dimensions, etc.)
 *
 * All state is computed once in the constructor. The view is fully immutable and thread-safe.
 * A new instance is created on every delta change, giving [kotlinx.coroutines.flow.MutableStateFlow]
 * a fresh object reference that always triggers emission.
 *
 * **Aliasing caveat:** the [ListingDirectory] base is held by reference and read live by [get]
 * (whole-row reads only, so never torn). When [com.imbric.core.ifs.directories.DirState.sortBy]
 * re-sorts the base in place, this view's reads are transiently reordered until DirState publishes
 * the rebuilt view microseconds later. The view's own state (mapping, deltas) stays immutable.
 *
 * **Zero-delta fast path:** when additions, deletions AND enrichments are all empty there is
 * nothing to merge, so rows are re-viewed through the base's own lazy [ListingDirectory.asList]
 * delegate — the same zero-overhead view a static directory read uses. No mapping array is
 * built and no base row is walked. Every rebuild still creates a new instance, so one rebuild
 * still produces exactly one view and the caller's revision/emission behavior is unchanged.
 */
class EnrichedListingView(
    private val base: ListingDirectory,
    private val comparator: Comparator<FileEntry>,
    private val additions: Map<String, FileInfo>,
    private val deletions: Set<String>,
    private val enrichments: Map<String, FileInfo>
) : AbstractList<FileEntry>() {

    private val additionsList: List<FileInfo>

    /**
     * Zero-delta delegate: the base listing's lazy view. Assigned only when
     * additions, deletions AND enrichments are all empty — rows then come
     * straight from the cached base, with no mapping array built at all.
     */
    private val passthrough: List<FileEntry>?

    /** Base-index → view-index mapping; null while [passthrough] is active. */
    private val mapping: IntArray?

    init {
        additionsList = additions.values.sortedWith(comparator)

        // Fast path: zero deltas of any kind — delegate to the base listing.
        // A fresh instance is still created on every rebuild, so identity-based
        // StateFlow emission and the caller's revision bump behave as today.
        if (additions.isEmpty() && deletions.isEmpty() && enrichments.isEmpty()) {
            passthrough = base.asList()
            mapping = null
        } else {
            passthrough = null

            // Fast path: no additions/deletions, only enrichment overlays.
            if (additions.isEmpty() && deletions.isEmpty()) {
                mapping = IntArray(base.size) { it }
            } else {
                // Two-pointer merge: base (skipping deletions/additions) + sorted additions
                val result = IntArrayList(base.size + additionsList.size)
                var baseIdx = 0
                var addIdx = 0

                while (baseIdx < base.size && addIdx < additionsList.size) {
                    val baseUri = base.getUri(baseIdx)

                    // Skip deleted or modified base entries (modified = in additions)
                    if (baseUri in deletions || baseUri in additions) {
                        baseIdx++
                        continue
                    }

                    val addEntry = additionsList[addIdx]
                    val cmp = comparator.compare(base.get(baseIdx), addEntry)
                    if (cmp <= 0) {
                        result.add(baseIdx)
                        baseIdx++
                    } else {
                        result.add(-(addIdx + 1))
                        addIdx++
                    }
                }

                // Drain remaining base entries
                while (baseIdx < base.size) {
                    val baseUri = base.getUri(baseIdx)
                    if (baseUri !in deletions && baseUri !in additions) {
                        result.add(baseIdx)
                    }
                    baseIdx++
                }

                // Drain remaining additions
                while (addIdx < additionsList.size) {
                    result.add(-(addIdx + 1))
                    addIdx++
                }

                mapping = result.toArray()
            }
        }
    }

    override val size: Int
        get() {
            val direct = passthrough
            if (direct != null) return direct.size
            // passthrough and mapping are assigned as a pair in init,
            // so mapping is non-null whenever passthrough is null.
            val mapped = requireNotNull(mapping) { "passthrough is null, so mapping must be non-null" }
            return mapped.size
        }

    override fun get(index: Int): FileEntry {
        val direct = passthrough
        if (direct != null) return direct[index]

        // passthrough and mapping are assigned as a pair in init,
        // so mapping is non-null whenever passthrough is null.
        val encoded = requireNotNull(mapping) { "passthrough is null, so mapping must be non-null" }[index]
        return if (encoded >= 0) {
            val uri = base.getUri(encoded)
            enrichments[uri] ?: base.get(encoded)
        } else {
            val additionIdx = -(encoded + 1)
            val addition = additionsList[additionIdx]
            enrichments[addition.uri] ?: addition
        }
    }

    // Identity equality — each instance is unique, forces StateFlow emission
    override fun equals(other: Any?): Boolean = this === other
    override fun hashCode(): Int = System.identityHashCode(this)

    private class IntArrayList(initialCapacity: Int) {
        private var data = IntArray(initialCapacity)
        var size: Int = 0
            private set

        fun add(value: Int) {
            if (size >= data.size) {
                data = data.copyOf(data.size * 2)
            }
            data[size++] = value
        }

        fun toArray(): IntArray = data.copyOf(size)
    }
}
