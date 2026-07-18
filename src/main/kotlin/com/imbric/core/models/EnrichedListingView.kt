package com.imbric.core.models

/**
 * Composite view that merges an immutable [ListingDirectory] snapshot with a delta layer.
 *
 * - **additions**: new/modified files from file events (not yet in the base snapshot)
 * - **deletions**: URIs of files that have been removed
 * - **enrichments**: files that have been enriched with metadata (emblems, dimensions, etc.)
 *
 * The view maintains a sorted `IntArray` mapping from composite index → source.
 * Positive values = base directory index, negative values = additions list index (-1 = 0).
 * Deletions are filtered out by skipping base entries whose URIs are in the deletions set.
 *
 * Thread-safe for reads: the base ListingDirectory is immutable, and the delta maps
 * are replaced atomically via [rebuild].
 */
class EnrichedListingView(
    private val base: ListingDirectory,
    private val comparator: Comparator<FileEntry>
) : AbstractList<FileEntry>() {

    // Delta layer — replaced atomically on rebuild()
    @Volatile private var additions: Map<String, FileInfo> = emptyMap()
    @Volatile private var deletions: Set<String> = emptySet()
    @Volatile private var enrichments: Map<String, FileInfo> = emptyMap()

    // Composite index mapping: compositeIndex → source
    // Positive = base array index, negative = -(additions sorted index + 1)
    @Volatile private var mapping = IntArray(0)
    @Volatile private var additionsList: List<FileInfo> = emptyList()

    override val size: Int get() = mapping.size

    override fun get(index: Int): FileEntry {
        val encoded = mapping[index]
        return if (encoded >= 0) {
            // Base entry — check enrichment first
            val uri = base.getUri(encoded)
            enrichments[uri] ?: base.get(encoded)
        } else {
            // Addition entry — already a FileInfo, check enrichment
            val additionIdx = -(encoded + 1)
            val addition = additionsList[additionIdx]
            enrichments[addition.uri] ?: addition
        }
    }

    /**
     * Rebuild the composite view with new deltas.
     * This is the only mutation method — it replaces all delta maps atomically.
     *
     * Uses a two-pointer merge algorithm (like merge-sort merge step) to insert
     * additions into the correct sorted position. O(N + A) where N = base size,
     * A = additions size.
     */
    fun rebuild(
        newAdditions: Map<String, FileInfo>,
        newDeletions: Set<String>,
        newEnrichments: Map<String, FileInfo>
    ) {
        additions = newAdditions
        deletions = newDeletions
        enrichments = newEnrichments

        // Fast path: no deltas → delegate directly to base
        if (newAdditions.isEmpty() && newDeletions.isEmpty()) {
            additionsList = emptyList()
            mapping = IntArray(base.size) { it }
            return
        }

        // Sort additions by the same comparator
        additionsList = newAdditions.values.sortedWith(comparator)

        // Two-pointer merge: base (skipping deletions) + additions
        val result = IntArrayList(base.size + additionsList.size)
        var baseIdx = 0
        var addIdx = 0

        while (baseIdx < base.size && addIdx < additionsList.size) {
            val baseUri = base.getUri(baseIdx)

            // Skip deleted or modified base entries (modified entries are in additions)
            if (baseUri in newDeletions || baseUri in newAdditions) {
                baseIdx++
                continue
            }

            val addEntry = additionsList[addIdx]
            val cmp = comparator.compare(base.get(baseIdx), addEntry)
            if (cmp <= 0) {
                // Base entry comes first (or equal)
                result.add(baseIdx)
                baseIdx++
            } else {
                // Addition comes first
                result.add(-(addIdx + 1))
                addIdx++
            }
        }

        // Drain remaining base entries (skip deletions and modifications)
        while (baseIdx < base.size) {
            val baseUri = base.getUri(baseIdx)
            if (baseUri !in newDeletions && baseUri !in newAdditions) {
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

    /** Check if a URI exists in the composite view (O(1) for base, O(log n) for additions). */
    fun containsUri(uri: String): Boolean {
        if (uri in deletions) return false
        if (uri in additions) return true
        return base.containsUri(uri)
    }

    /**
     * Fast IntArrayList for building the mapping without boxing.
     * Avoids ArrayList<Int> overhead (no autoboxing of primitives).
     */
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
