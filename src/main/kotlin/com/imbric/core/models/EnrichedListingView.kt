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
 */
class EnrichedListingView(
    private val base: ListingDirectory,
    private val comparator: Comparator<FileEntry>,
    private val additions: Map<String, FileInfo>,
    private val deletions: Set<String>,
    private val enrichments: Map<String, FileInfo>
) : AbstractList<FileEntry>() {

    private val additionsList: List<FileInfo>
    private val mapping: IntArray

    init {
        additionsList = additions.values.sortedWith(comparator)

        // Fast path: no deltas
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

    override val size: Int get() = mapping.size

    override fun get(index: Int): FileEntry {
        val encoded = mapping[index]
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

    /** Check if a URI exists in the composite view. */
    fun containsUri(uri: String): Boolean {
        if (uri in deletions) return false
        if (uri in additions) return true
        return base.containsUri(uri)
    }

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
